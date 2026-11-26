# Technical documentation

This document explains every module in plain language and records the engineering
decisions behind it, so each part can be defended in a review.

## 1. Core

### 1.1 Schemas (`app/core/schemas.py`)
Every object that moves between components is a Pydantic model: `DocumentRecord`, `Chunk`,
`InterviewAnalysis`, `TopicGroundability`, `RequirementsDocument`, `ApprovalRecord`,
`AgentDefinition`, `AgentAnswer`, `RuntimeResponse`, `EvalCase`, `CaseResult`, `Scorecard`,
`IterationRecord`, `FactoryRun`, `BudgetLimits/Usage`. Validators enforce rules such as:
requirements must have a purpose, audience, scope, sources and acceptance criteria;
out-of-scope cases must require refusal; answerable cases must have expected facts;
`chunk_overlap < chunk_size`; at most five interview questions.

### 1.2 LLM service (`app/core/llm_service.py`)
One interface (`LLMService`) with a provider protocol. `OllamaProvider` calls
`/api/chat` with the configured model, temperature, `num_predict` (max tokens), context
size, seed and timeout. `generate_json(messages, Schema)` passes the JSON schema to
Ollama's structured-output `format`, extracts JSON even from fenced or chatty replies,
validates with Pydantic and, on failure, retries with the validation error appended
(`LLM_MAX_RETRIES`). Adding another provider means implementing one `chat` method.
`ScriptedProvider` lets the unit tests run the real logic without a model.

### 1.3 Budget manager (`app/core/budget_manager.py`)
Counts real LLM calls, prompt/completion tokens (from Ollama's `prompt_eval_count` and
`eval_count`), elapsed time and iterations, per stage. `check()` runs before every LLM
call and raises `BudgetExceeded`; `can_afford()` runs before each optimisation iteration
using the measured cost of the previous evaluation. The run records why it stopped.

### 1.4 Orchestrator (`app/core/orchestrator.py`)
A stage machine. `start` (ingestion + interview), `answer` (groundability + tools +
requirements), `decide` (human approval), `execute` (everything after approval, unattended).
After each stage it saves `run_state.json`, updates `factory_runs`, writes an audit entry,
and only then marks the stage completed. Exceptions mark the stage failed with the error.

## 2. Document ingestion (`app/ingestion/`)
* `loader.py`: sanitises file names (no path traversal), allows only configured
  extensions, enforces the size limit, checks magic bytes (`%PDF`, zip for DOCX) and text
  decodability, and hashes content (SHA-256).
* `parser.py`: PyMuPDF for PDF (per page, heading detection, rejects encrypted/scanned
  PDFs with a clear message), python-docx for DOCX (headings and tables as
  `column: value` rows), pandas for CSV (every row becomes `[file row N] col: val; ...`,
  so column names and row numbers are preserved), plain text with heading heuristics.
* `chunker.py`: recursive splitting on configurable separators with size and overlap.
  CSV rows are grouped without ever splitting a row and keep `row_start/row_end`.
  Chunk IDs are `<content-hash>-<index>`, so re-ingesting an unchanged file is idempotent.
* `embeddings.py`: sentence-transformers `all-MiniLM-L6-v2`, normalised vectors. When
  PyTorch cannot load (seen with Windows Smart App Control), the same model runs through
  ONNX Runtime with identical mean pooling and normalisation.
* `vector_store.py`: ChromaDB persistent client, cosine space, one collection per
  project and chunking configuration, so the optimizer can re-chunk without destroying
  the index used by earlier versions.
* `pipeline.py`: `KnowledgeBase.ingest` = validate, de-duplicate identical content,
  detect added/modified/unchanged/removed files by hash, parse, chunk, embed, upsert,
  upload the original to Supabase Storage, and write `documents` + `document_versions`.
  Changes are propagated to every collection of the project.

## 3. Factory

### 3.1 Intake interviewer
The LLM receives the brief and an inventory of the documents (name, type, size, pages,
CSV columns, an extracted preview). It returns purpose, audience, requested topics,
ambiguities, missing information and at most five questions. Two deterministic filters
follow: near-duplicate questions (token Jaccard >= 0.75) are dropped, and questions whose
best retrieved passage has similarity >= 0.62 are dropped as "answered by the documents".
All kept and dropped questions are saved.

### 3.2 Groundability guard
For each requested topic: retrieve the top passages (topic, and topic + purpose). If the
best similarity is below 0.25 the topic is unsupported without an LLM call. Otherwise the
LLM states, passage by passage, whether it contains concrete facts about the topic
(per-passage yes/no is far more reliable for a 3B model than one holistic label; this was
changed after live testing showed the model over-using "ambiguous"). Rules turn those
verdicts into supported / partially supported / ambiguous (contradiction) / unsupported.
Passage ids not in the retrieved set are discarded, which defends against the model
inventing evidence.

### 3.3 Requirements manager
The LLM writes scope, tone, response format, limitations and acceptance criteria.
Everything else is deterministic: supported and must-answer topics come from the
groundability matrix, unsupported topics are always must-refuse, knowledge sources are
the ingested files, tools come from the tool selector. If the LLM proposes an extra
must-refuse topic, it is kept only if the documents do not support it (checked with the
same guard). Live testing showed why: the model once listed every supported topic as
must-refuse after misreading a clarification answer. Dropped proposals are recorded in
`decision_notes`.

### 3.4 Human approval checkpoint
Requirements are shown in full; editable fields can be changed (knowledge sources and
groundability cannot). Approve or reject; both store the edited requirements as a new
version, an `approval_records` row (approver, timestamp, comment, field-level diff
against the original) and an audit entry. The gate is enforced three times:
`approval_manager.require_approval` in `execute`, `Repository.save_agent_version`, and a
database trigger on `agent_versions`. Approval records and evaluation results are
append-only (database triggers).

### 3.5 Tool registry and selection
Four independent tools, each with a Pydantic input and output schema, an execution
function, error handling and availability rules:
`csv_lookup` (keyword + column filters, returns rows with `file row N` references; only
available when a CSV source exists), `calculator` (AST-restricted arithmetic, no `eval`),
`weather_api` (Open-Meteo; only two allow-listed URLs; 8 s timeout; output validated),
`current_date` (IANA timezone, timezone-aware). The selector asks the LLM to decide per
tool from the requirements and each tool's generic "when needed" description, then
applies availability rules. A `ToolBox` built from the agent definition is the only way
the runtime can call a tool.

### 3.6 Agent generator and RAG configuration
Retrieval settings are derived from measured document statistics (amount of prose, median
chunk length, number of documents, presence of tables). The LLM writes identity,
objective, knowledge boundaries, ambiguity rules, style rules and tool rules; the
grounding, citation, refusal and output-format sections are fixed templates so they are
always present. The result is validated as `AgentDefinition` and stored as version 1 with
its structured prompt parts (so the optimizer can change one section).

## 4. Runtime (`app/runtime/`)
`AgentRuntime` loads any valid definition. Per question: retrieve (top-k, threshold,
optional metadata filters, approved sources only); if tools are attached, a planning call
chooses tool calls which the `ToolBox` executes; if no evidence passes the threshold and
no tool produced output, the policy refuses without calling the model; otherwise the model
answers in the JSON contract. `output_validator` checks required fields, removes citations
that are not in the retrieved evidence, requires a citation for factual answers and a
reason for refusals, enforces the length limit and optionally rejects numbers not present
in the evidence; violations trigger a controlled retry. Chat sessions are bound to one
agent and project.

## 5. Evaluation

### 5.1 Generator
Chunks are sampled round-robin across documents with a fixed seed. Per chunk the LLM
writes one question and copies key facts word-for-word. Every fact is verified against
the source chunk (normalised substring, or >= 85% content-word recall with all numbers
present). Cases without a verified fact are rejected and kept in `rejected_candidates`.
Multi-document cases pair a chunk with the most similar chunk from another document and
require verified facts from both. Edge cases: false premise, ambiguous, incomplete,
paraphrased, partial information. Out-of-scope questions are rejected if retrieval finds
strongly related evidence (similarity >= 0.55). Temperature 0. Prompts are committed in
`prompts/eval_generator*.txt`.

### 5.2 Judge
Deterministic checks: refusal, fact matching (numbers must match), numbers in the answer
that are not in the evidence, valid/expected citations, contract validity, whether the
expected facts were retrieved at all, tool errors. LLM judge (separate model): grounding,
factual, scope (0 / 0.5 / 1, with reasons), behaviour met, a supporting quote and a list
of unsupported claims. Combination rules (in `evaluator.score_case`):
* grounding = min(deterministic, judge); the judge's grounding is capped at 0.5 when its
  quote is not found in the evidence;
* factual = mean(deterministic fact recall, judge factual);
* refusal, citation and contract metrics are deterministic;
* pass rules per category require the deterministic conditions; the judge alone can never
  pass an answer.
Bias defences: different model family for the judge; fixed rubric and temperature 0
across iterations; the rubric says length earns nothing; expected facts are given as
"points to check", not as a model answer; baseline comparisons judge each pair in both
orders and count only consistent verdicts.

### 5.3 Failure classifier
Ordered rules map each failed case to retrieval miss, prompt defect, hallucination, wrong
refusal, tool defect or output-contract defect, with a written explanation.

## 6. Optimisation
See `prompts/optimizer.txt` and `SYSTEM_ARCHITECTURE.md` section 4. Each category may
change only its mapped fields; critic rules containing an expected fact or number from
the dataset are rejected to avoid leaking answers into the prompt. Every change is a
`change_logs` row with old value, new value and reason. The whole dataset is re-run so
regressions are visible, and the best version is kept.

## 7. Reporting and artifacts
`report_generator` builds the final report only from measured scorecards and results:
pass rate, the six metrics (with the number of cases each applies to), the composite
(labelled as derived, with its formula), category results, iteration table, changes,
regressions, remaining failures, groundability, limitations, dataset statistics and
budget. `honest_summary` writes sentences like "The agent achieved a 78% evaluation pass
rate ... Remaining failures were primarily ...". The PDF is rendered by ReportLab from the
same Markdown. `ArtifactManager` writes each artifact to `artifacts/runs/<slug>/`, uploads
it to Supabase Storage and records its SHA-256.

## 8. Regression
`run_regression` re-ingests the new document set (hash comparison gives
added/modified/removed), keeps the old dataset, re-runs it against the delivered agent,
and compares per test. A newly failing test whose expected facts no longer appear in the
updated documents is reported as a *stale test*, not as an agent regression. Results go to
a new `regression_<timestamp>/` folder and a `regression_runs` row.

## 9. Security
Secrets only in `.env` (git-ignored); `.env.example` documents every variable. The
service-role key stays in the API process. Supabase Auth issues user sessions; the API
validates the bearer token and checks project ownership on every request; RLS protects
direct database access. Uploads are validated (type, size, magic bytes, names). Artifact
downloads are confined to the run folder. The weather tool only calls two allow-listed
URLs with a timeout.

## 10. Known limitations
* A 3B local model is the agent, factory and (another 3B) judge; it sometimes misreads
  instructions, which is why so many decisions are deterministic.
* Expected facts are verified to exist in the source, but the *question* written for them
  can still be imperfect.
* Groundability works per requested topic; topics the brief never names (for example a
  salary question in an HR brief that does not mention salary) are handled at answer time
  by the evidence threshold and refusal rules.
* No OCR for scanned PDFs.
* Background jobs run in the API process (no external queue).
