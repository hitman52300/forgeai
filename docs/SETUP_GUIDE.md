# Setup guide (Windows; Linux/macOS analogous)

## 1. Prerequisites

| Requirement | Tested version |
|---|---|
| Python | 3.14.3 (3.11+ should work) |
| Ollama | 0.40.x, running on `http://localhost:11434` |
| Git | 2.53 |
| GPU (optional) | NVIDIA GTX 1650 4 GB used during development; CPU works but is slower |
| Supabase | a hosted project (free tier is enough) |

## 2. Install

```powershell
git clone <repo> C:\ForgeAI
cd C:\ForgeAI
py -3.14 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
ollama pull qwen2.5:3b
ollama pull llama3.2:3b
```

The embedding model `sentence-transformers/all-MiniLM-L6-v2` (~90 MB) downloads from
Hugging Face on first use.

**Windows Smart App Control.** On the development machine, Smart App Control first
blocked PyTorch's DLL (`torch_python.dll`). `app/ingestion/embeddings.py` falls back to
running the same model through ONNX Runtime when PyTorch cannot load, so ingestion keeps
working. Do not disable Smart App Control for this project.

## 3. Configure

Copy `.env.example` to `.env` and fill in:

* `SUPABASE_URL`, `SUPABASE_ANON_KEY` (Project settings -> API)
* `SUPABASE_SERVICE_ROLE_KEY`: server-side only. Never commit it, and never put it in the UI.
* `FORGEAI_OPERATOR_EMAIL`: the Supabase Auth user that owns runs started from the CLI.
* Model, temperature, max tokens, timeout and retry limit (`LLM_*`), budget limits (`BUDGET_*`),
  and the quality target (`QUALITY_TARGET`).

`STORAGE_BACKEND=local` runs without Supabase (JSON files under `data/local_db`). The
tests use this mode.

## 4. Database

In the Supabase SQL editor, run `app/database/migrations/001_init_schema.sql`, then
`002_rls_and_storage.sql`. (`000_drop_legacy.sql` only removes an older prototype schema.)
This creates 22 tables with RLS, the approval trigger, append-only triggers and the two
private storage buckets.

## 5. Run

### One click
Double-click **`ForgeAI.exe`** in the ForgeAI folder (or **`Start-ForgeAI.cmd`**). The
launcher creates the Python environment and installs packages on first start, starts
Ollama if it is installed but not running, downloads missing models, starts the API
(port 8000) and the UI (port 8501), and opens the browser. Close its window to stop.
Logs: `data/logs/`.

It cannot bundle: the Ollama program (install once from ollama.com), the model weights
(downloaded by the launcher on first start), Python itself (needed once to create the
environment) and the Supabase project (cloud; values in `.env`).

On the development PC, Windows Smart App Control blocks unsigned executables, including
the locally built `ForgeAI.exe`. `Start-ForgeAI.cmd` runs the same launcher through the
signed Python interpreter and was verified to start both servers. A code-signing
certificate would be needed for the .exe to run under Smart App Control. Rebuild the exe
with `scripts\build_exe.cmd`.

### Manually

```powershell
# terminal 1: API
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
# terminal 2: UI
.venv\Scripts\python.exe -m streamlit run frontend/Home.py
```

Open http://localhost:8501, create an account in the sidebar (Supabase Auth), then sign in.
Check http://localhost:8000/health: Ollama must report both models.

## 6. Tests

```powershell
.venv\Scripts\python.exe -m pytest tests -q
```

Unit and integration tests run offline with a scripted LLM, real embeddings and real
ChromaDB. `tests/evaluation/test_live_factory.py` runs the real factory against Ollama
on a small unseen corpus; it is skipped when Ollama is not reachable.

## 7. Rebuild demo documents

```powershell
.venv\Scripts\python.exe scripts\build_demo_documents.py
```
