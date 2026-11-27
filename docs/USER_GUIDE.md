# User guide

## 1. Sign in
Open the UI (http://localhost:8501). In the sidebar, create an account or sign in
(Supabase Auth). You only ever see your own projects, runs and agents.

## 2. Create New Agent
Enter a project name, a one-paragraph brief, and upload the knowledge documents
(TXT, PDF, DOCX, CSV; 20 MB per file by default). Choose how many evaluation cases to
generate (15-40) and press **Start interview**. ForgeAI validates and indexes every file;
rejected files are listed with the reason (wrong type, empty, too large, not a real PDF,
password protected, no extractable text).

## 3. Interview
ForgeAI shows what it understood (purpose, audience, topics, ambiguities) and up to five
clarifying questions. Questions that the documents already answer were dropped; the
dropped list explains why. Answer and press **Submit answers**. ForgeAI then checks
groundability and writes the requirements.

## 4. Requirements Review (mandatory)
* **Requirements tab**: every editable field. Lists are one item per line.
* **Groundability matrix**: each requested topic with evidence and status. Unsupported
  topics are refused by the agent; upload documents if you need them answered.
* **Approval history**: every decision, who made it, when, and a field-by-field comparison.

Press **Approve** or **Reject and keep editing**. Nothing is generated before approval.

## 5. Factory Execution
After approval, press **Run factory (unattended)**. The pipeline shows real stage statuses
(pending, running, completed, failed, awaiting approval) with messages, LLM calls, tokens,
time and iterations. A run can stop early because the quality target was reached, there
was no measurable improvement, the budget ran out, or three iterations were done; the stop
reason is shown.

## 6. Evaluation Dashboard
Choose a scorecard (one per evaluation). You see total, passed and failed cases, the case
pass rate, the six quality metrics, the composite score (always labelled as derived),
failure categories, per-category results, the iteration comparison, every change the
optimizer made, and every case with its answer, expected facts, metric explanations and
source evidence.

## 7. Agent Studio
Inspect each agent version: system prompt, retrieval configuration, attached tools,
output contract, refusal policy, runtime options and the version history with the change
summary. Download the definition as JSON.

## 8. Agent Chat Runner
Pick a delivered agent and ask questions. Each answer shows citations, confidence,
refusals with their reason (and whether the model or the evidence policy refused),
retrieved passages and tool outputs. History belongs to that agent only.

Outside the UI: `python scripts/run_agent.py artifacts/agents/<agent_id>/final.json`.

## 9. Reports and Artifacts
Download every artifact of a run (requirements, groundability, approval record, agent
definitions, dataset, results, scorecards, iteration log, change log, final report in
Markdown and PDF). For a completed run, upload a changed document set under
**Regression mode** to re-run the old tests; a new regression report is created and
nothing old is overwritten.
