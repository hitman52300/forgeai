# ForgeAI — The Agent That Builds Agents

ForgeAI is an agent engineering factory. Give it a one-paragraph brief and a folder of
documents; it interviews you (at most five questions), checks which requested topics the
documents can actually support, writes a requirements document that **a human must
approve**, generates a versioned agent definition, generates and verifies its own
evaluation dataset, tests the agent, classifies the failures, applies targeted fixes for
up to three iterations, and delivers a runnable agent with an honest quality report.

Everything runs locally on open-weight models through Ollama; Supabase stores the
structured data and files; ChromaDB stores the vectors.

## Quick start

```powershell
py -3.14 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
ollama pull qwen2.5:3b; ollama pull llama3.2:3b
copy .env.example .env      # then fill in the Supabase values
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
.venv\Scripts\python.exe -m streamlit run frontend/Home.py
```

Full instructions: [docs/SETUP_GUIDE.md](docs/SETUP_GUIDE.md).

## What is where

| Path | Contents |
|---|---|
| `app/` | backend: `core` (schemas, LLM service, budget, orchestrator), `ingestion`, `factory`, `tools`, `runtime`, `evaluation`, `optimization`, `regression`, `reporting`, `database`, `api` |
| `frontend/` | Streamlit UI (dashboard + 8 pages) |
| `prompts/` | every generation, judging, critic and dataset-synthesis prompt |
| `data/demos/` | the two demonstration document collections, their source text and briefs |
| `artifacts/runs/` | the evidence of real factory runs (requirements, approvals, agents, datasets, results, scorecards, iteration logs, reports) |
| `baseline/` | the manually written baseline agent |
| `scripts/` | CLI (`forgeai_cli.py`), standalone agent runner, baseline comparison, demo builders |
| `tests/` | unit, integration, live evaluation tests |
| `docs/` | architecture, database, API, setup, user, technical, demonstration and presentation guides, final report |

## Documentation

* [System architecture](docs/SYSTEM_ARCHITECTURE.md)
* [Database schema](docs/DATABASE_SCHEMA.md)
* [API](docs/API_DOCUMENTATION.md)
* [Setup guide](docs/SETUP_GUIDE.md)
* [User guide](docs/USER_GUIDE.md)
* [Technical documentation](docs/TECHNICAL_DOCUMENTATION.md)
* [Demonstration guide](docs/DEMONSTRATION_GUIDE.md)
* [Presentation guide](docs/PRESENTATION_GUIDE.md) and [script](docs/PRESENTATION_SCRIPT.md)
* [Final project report (PDF)](docs/FINAL_PROJECT_REPORT.pdf)

## Honesty rules the code enforces

* No stage is shown as completed before it completed; failures are recorded with reasons.
* Expected facts in the evaluation dataset must be traceable to a source chunk, or the
  case is rejected (and the rejection is saved).
* An answer cannot pass on the LLM judge alone; deterministic checks must also pass.
* Reports are generated only from measured scorecards; failed cases are listed.
* Evaluation results and approval records are append-only.
