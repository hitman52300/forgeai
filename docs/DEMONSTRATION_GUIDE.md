# Demonstration guide

## 1. Before the demo (10 minutes)

```powershell
ollama list                                   # qwen2.5:3b and llama3.2:3b present
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
.venv\Scripts\python.exe -m streamlit run frontend/Home.py
```
Open http://localhost:8000/health (Ollama ok, database ok) and http://localhost:8501,
sign in.

## 2. Show the evidence of the committed demo runs

| Demo | Folder |
|---|---|
| HR policy assistant | `artifacts/runs/hr_demo/` |
| Ship-spares procurement assistant | `artifacts/runs/procurement_demo/` |
| Factory vs manual baseline | `artifacts/runs/hr_demo/baseline_comparison/` |
| Regression after a policy change | `artifacts/runs/hr_demo/regression_*/` |

Each run folder contains `input_brief.md`, `document_manifest.json`, `interview.json`,
`requirements_original.json`, `requirements.json`, `requirements.md`,
`groundability_report.json`, `approval_record.json`, `approval_history.json`,
`agent_definition_v*.json`, `agent_definition_final.json`, `evaluation_dataset.json`,
`evaluation_results_initial.json`, `evaluation_results_iter*.json`,
`evaluation_results_final.json/.csv`, `iteration_logs.json`, `change_log.json`,
`scorecards.json`, `failure_classification.json`, `budget.json`, `final_report.md`,
`final_report.pdf`, `runnable_agent.json`. The measured numbers are summarised in
`docs/FINAL_PROJECT_REPORT.pdf` (chapter 9).

## 3. Live sequence (about 15 minutes of interaction, plus waiting for the run)

1. **Dashboard**: totals, average pass rate, runs needing attention.
2. **Create New Agent**: paste the reviewer's brief, upload their folder. Point out the
   file validation messages if a file is rejected.
3. **Interview**: show the understood purpose/topics and the at-most-five questions;
   open "dropped questions" to show questions removed because the documents answer them.
4. **Requirements Review**: open the groundability matrix (evidence + status). Edit one
   field (for example the tone), show the pending edit, press **Reject** with a comment,
   then **Approve**. Open *Approval history* to show the diff, approver and time.
5. **Factory Execution**: before approval, the execute button is not offered and the API
   returns 409. After approval press **Run factory (unattended)** and show stages moving
   from pending to running to completed.
6. While it runs, use the committed HR run:
   * **Evaluation Dashboard**: pass rate vs metrics vs composite; failure categories; open
     a failed case and show the answer, expected facts, the metric explanations and the
     retrieved evidence; show the iteration comparison and the change list.
   * **Agent Studio**: system prompt sections, retrieval config, attached tools (HR: no
     weather tool), version history with changes.
   * **Agent Chat**: ask a supported question (cited), an unsupported one (salary:
     refused with reason), a question with a false premise, and a vague question.
   * **Reports and Artifacts**: download the PDF report.
7. When the reviewer's run finishes, open its Evaluation Dashboard and final report and
   read the honest summary sentence.

## 4. Suggested chat questions (HR agent)

* "How many days of annual leave do I get per year?" (supported, cited)
* "Can I carry forward 20 days of annual leave?" (false premise: limit is 15)
* "What is my salary band?" (unsupported: refuse)
* "How do I report it?" (vague: should ask what "it" refers to)
* "If I arrive at 09:50 three times this month, what happens?" (cross-rule: late marks)

## 5. Suggested chat questions (procurement agent)

* "Which suppliers offer SP-3002 and at what price?"
* "Compare the payment terms of Alpha and Beta."
* "Is SP-2003 in stock?"
* "Can Beta deliver SP-1005 to Singapore by Friday?" (unsupported delivery claim: refuse)
* "What is the set pressure of SP-5003 from Beta?" (ambiguous: two variants)

## 6. If something goes wrong

| Symptom | Explanation / action |
|---|---|
| `/health` shows Ollama error | start Ollama; `ollama list` must show both models |
| Run stops with "budget exhausted" | this is the budget manager working; the stop reason is in the run; raise `BUDGET_*` |
| Evaluation dataset < 20 cases | the generator rejected too many unverifiable candidates (small corpus); the run is marked failed instead of pretending |
| Slow answers | a 3B model on a 4 GB GPU: about 10 s per answer; evaluation of 35 cases takes 10-15 minutes |
| A supported question is refused | show the retrieved evidence and similarity; this is a retrieval miss and the optimizer's retrieval fixes target exactly this |
