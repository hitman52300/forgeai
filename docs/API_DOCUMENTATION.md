# API documentation

Base URL `http://localhost:8000`. Interactive docs: `/docs` (OpenAPI). With
`STORAGE_BACKEND=supabase`, every endpoint except `/health` and `/tools` needs
`Authorization: Bearer <Supabase access token>`; resources of other users return 404.
Long operations return a `job_id`; poll `GET /jobs/{job_id}`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | storage backend, models, Ollama reachability |
| GET | `/tools` | tool registry specs (name, description, input/output schema, permission) |
| GET | `/projects` | projects of the current user |
| POST | `/projects/runs` | multipart: `name`, `brief`, `target_cases`, `files[]` -> job (ingestion + interview) |
| GET | `/projects/{id}/documents` | documents with version history |
| GET | `/runs` | runs of the current user |
| GET | `/runs/{run_id}` | run record (stages, messages, usage, budget) + artifact names |
| GET | `/runs/{run_id}/interview` | analysis, questions, dropped questions, answers |
| POST | `/runs/{run_id}/interview/answers` | `{"answers": {"<question_id>": "..."}}` -> job (groundability + requirements) |
| GET | `/runs/{run_id}/requirements` | current, original, tool selection, groundability |
| GET | `/runs/{run_id}/requirements/versions` | stored requirement versions |
| POST | `/runs/{run_id}/approval` | `{"decision": "approved"|"rejected", "approver_name", "edits": {...}, "comment"}` |
| GET | `/runs/{run_id}/approval/history` | all decisions with diffs |
| POST | `/runs/{run_id}/execute` | 409 unless approved -> job (generation, evaluation, optimisation, delivery) |
| GET | `/jobs/{job_id}` | status, progress messages, result or error |
| GET | `/runs/{run_id}/evaluation/dataset` | evaluation dataset incl. rejected candidates |
| GET | `/runs/{run_id}/evaluation/scorecards` | per-iteration scorecards |
| GET | `/runs/{run_id}/evaluation/results/{initial|final|N}` | case-level results |
| GET | `/runs/{run_id}/evaluation/iterations` | iteration records and change log |
| GET | `/runs/{run_id}/artifacts` | artifact list |
| GET | `/runs/{run_id}/artifacts/{path}` | download (path confined to the run folder) |
| POST | `/runs/{run_id}/regression` | multipart `files[]` (the full new document set) -> job |
| GET | `/agents` | agents of the current user |
| GET | `/agents/{agent_id}/versions` | all versions with definitions |
| POST | `/agents/{agent_id}/chat` | `{"question", "session_id", "version"?}` -> `RuntimeResponse` |
| DELETE | `/agents/{agent_id}/chat/{session_id}` | reset a conversation |

## RuntimeResponse

```json
{"agent_id": "...", "agent_version": 2, "question": "...",
 "answer": {"answer": "...", "citations": ["leave_policy.pdf"], "refused": false, "refusal_reason": "",
            "confidence": 0.8, "needs_clarification": false, "tool_calls": []},
 "retrieved": [{"source_filename": "leave_policy.pdf", "chunk_id": "...", "location": "p.1", "score": 0.61, "excerpt": "..."}],
 "tool_results": [], "contract_valid": true, "contract_errors": [], "refusal_applied_by": "none|model|policy",
 "latency_s": 6.2, "llm_calls": 1}
```

The same factory is available from the command line: `scripts/forgeai_cli.py`
(start / answer / approve / reject / execute / status).
