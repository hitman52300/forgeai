# ForgeAI — Pre-build plan

## 1. Environment (inspected 2026-11-27)

| Item | Found |
|---|---|
| OS | Windows 11, 16 GB RAM |
| GPU | NVIDIA GTX 1650 Max-Q, 4 GB VRAM (+ Intel UHD) |
| Python | 3.14.3 (via `py` launcher; `python` alias not on PATH) → project venv `.venv` |
| Git | 2.53 (folder was empty, not yet a repo) |
| Ollama | 0.40.18, server running on :11434, **no models pulled** |
| Docker | present (not required) |
| Supabase | project `forgeai` exists (ACTIVE). It already contains an older, empty schema (alembic `0004`: users, roles, refresh_tokens, agent_runs, human_approvals, …) whose table names differ from the spec. |
| Wheels | torch 2.15, chromadb 1.5.9, sentence-transformers 6.3, pymupdf 2.2 all publish wheels for Python 3.14 |

## 2. Architecture (concise)

ForgeAI is a pipeline of small services orchestrated by `core/orchestrator.py`.
Every hand-off between stages is a Pydantic model from `core/schemas.py`, and
every stage writes its output as an artifact (local `artifacts/runs/<run>/` +
Supabase Storage) and a row in Supabase.

```
Brief + docs ──► Ingestion ──► Interviewer (≤5 Qs) ──► Requirements Manager
                    │                                        │
                 ChromaDB ◄──── Groundability Guard ◄────────┘
                                         │
                              Human Approval Checkpoint  (hard gate, DB-checked)
                                         │
             Tool Registry ──► Agent Generator (versioned JSON definition)
                                         │
                              Evaluation Generator (≥20 cases, facts verified
                                         │            against source chunks)
                     ┌──────► Agent Runtime (generic) ──► Judge (deterministic + LLM)
                     │                                         │
                Optimizer ◄── Critic / Failure Classifier ◄────┘
               (≤3 iters, Budget Manager, targeted diffs only)
                                         │
                       Reporting Engine + Artifact Manager ──► Chat Runner
```

- **LLM service**: one `LLMService` interface; `OllamaProvider` implements it
  (model, base URL, temperature, max tokens, timeout, retries configurable).
  `generate_json(prompt, schema)` uses Ollama JSON mode, validates with
  Pydantic, and retries with the validation error fed back.
- **Generator vs judge model**: agent runs on model A, the judge on model B
  (configurable) to reduce self-preference bias.
- **Persistence**: a `Repository` interface with a Supabase implementation
  and a local JSON implementation (used by offline unit tests). The factory
  never talks to Supabase directly.
- **No domain logic**: nothing references HR, procurement, filenames or demo
  names. Tool choice comes from the requirements + registry descriptions +
  document types.

## 3. Database schema (Supabase Postgres, schema `public`)

All tables: `id uuid pk default gen_random_uuid()`, `created_at timestamptz`,
owner via `project_id → projects.owner_id → auth.users`. RLS: a row is visible
only if its project's `owner_id = auth.uid()`.

| Table | Key columns |
|---|---|
| profiles | id = auth.users.id, display_name, role |
| projects | owner_id, name, brief, status |
| documents | project_id, filename, file_type, size_bytes, storage_path, current_hash, status |
| document_versions | document_id, version, content_hash, chunk_count, change_type |
| factory_runs | project_id, status, current_stage, stage_statuses jsonb, budget jsonb, usage jsonb, stop_reason |
| requirements | run_id, version, kind (original/edited/approved), content jsonb |
| approval_records | run_id, requirements_id, decision, approver_id, comment, diff jsonb |
| agent_definitions | project_id, run_id, agent_name, latest_version |
| agent_versions | agent_definition_id, version, definition jsonb, parent_version, change_summary |
| evaluation_datasets | run_id, version, case_count, generation_config jsonb |
| evaluation_cases | dataset_id, test_id, category, question, expected jsonb, must_refuse, difficulty |
| evaluation_results | run_id, agent_version_id, case_id, iteration, passed, scores jsonb, answer jsonb, evidence jsonb |
| optimization_iterations | run_id, iteration, score_before, score_after, changes jsonb, decision |
| failure_records | result_id, category, explanation |
| tool_registry | name, description, input_schema, output_schema, enabled |
| regression_runs | project_id, base_run_id, doc_changes jsonb, summary jsonb |
| artifacts | run_id, kind, storage_path, sha256 |
| audit_logs | actor_id, run_id, action, details jsonb |
| baseline_comparisons | run_id, factory_version_id, baseline_name, results jsonb |

Indexes on every FK plus `(run_id, iteration)`. Storage buckets:
`documents` and `deliverables` (private, RLS by project folder).

## 4. Implementation plan

Follows the spec's ten phases. Each phase ends with pytest runs, and results
are reported as measured. Demo artifacts (Phase 7) are produced by actually
running the factory; the human approval in those runs is recorded as given by
the operator through the API/UI.

## 5. Dependencies and configuration

Python: fastapi, uvicorn, pydantic(-settings), httpx, streamlit, pandas,
pymupdf, python-docx, chromadb, sentence-transformers, supabase, reportlab,
pytest (see `requirements.txt`).

Models: Ollama `qwen2.5:3b` (agent/factory, ~1.9 GB) and `llama3.2:3b`
(judge, ~2.0 GB); embeddings `sentence-transformers/all-MiniLM-L6-v2` (~90 MB).

`.env`: `OLLAMA_BASE_URL, LLM_MODEL, JUDGE_MODEL, LLM_TEMPERATURE,
LLM_MAX_TOKENS, LLM_TIMEOUT_S, LLM_MAX_RETRIES, EMBEDDING_MODEL,
CHROMA_DIR, SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY,
MAX_UPLOAD_MB, BUDGET_*`.
