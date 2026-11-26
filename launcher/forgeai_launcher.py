"""ForgeAI.exe - one-click launcher (standard library only, packaged with PyInstaller).

Double-click ForgeAI.exe in the ForgeAI folder. It:
  1. finds the ForgeAI folder (the folder containing the exe, or its parent),
  2. on first run creates the Python environment and installs requirements.txt,
  3. checks Ollama; starts `ollama serve` if Ollama is installed but not running,
     and pulls the configured models if they are missing,
  4. starts the API (port 8000) and the UI (port 8501), waits until both answer,
  5. opens the UI in the default browser,
  6. stops both servers when this window is closed or Ctrl+C is pressed.

What it cannot bundle: Ollama itself (a separate Windows install), the model weights
(downloaded once by Ollama), Python (needed once to create the environment), and the
Supabase project (a cloud service configured in .env).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

API_PORT, UI_PORT = 8000, 8501
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def say(msg: str) -> None:
    print(f"[ForgeAI] {msg}", flush=True)


def fail(msg: str) -> None:
    say("ERROR: " + msg)
    input("\nPress Enter to close this window...")
    sys.exit(1)


def root_dir() -> Path:
    here = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent
    for cand in (here, here.parent, here.parent.parent):
        if (cand / "app" / "main.py").exists() and (cand / "requirements.txt").exists():
            return cand
    fail(f"could not find the ForgeAI folder next to {here}. Put ForgeAI.exe in the ForgeAI folder.")
    raise SystemExit


def read_env(root: Path) -> dict:
    env = {}
    for name in (".env", ".env.example"):
        f = root / name
        if f.exists():
            for line in f.read_text(encoding="utf-8-sig").splitlines():
                if "=" in line and not line.lstrip().startswith("#"):
                    k, v = line.split("=", 1)
                    env.setdefault(k.strip(), v.strip())
    return env


def http_ok(url: str, timeout: float = 3) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


def find_python() -> list[str]:
    for cmd in (["py", "-3.14"], ["py", "-3"], ["python"]):
        try:
            if subprocess.run(cmd + ["--version"], capture_output=True, creationflags=CREATE_NO_WINDOW).returncode == 0:
                return cmd
        except OSError:
            continue
    fail("Python 3.11+ was not found. Install Python from python.org once, then start ForgeAI.exe again.")
    return []


def ensure_venv(root: Path) -> Path:
    py = root / ".venv" / "Scripts" / "python.exe"
    marker = root / ".venv" / ".forgeai_installed"
    req = root / "requirements.txt"
    if py.exists() and marker.exists() and marker.read_text() == str(req.stat().st_mtime):
        return py
    if not py.exists():
        say("first start: creating the Python environment (one time)...")
        subprocess.run(find_python() + ["-m", "venv", str(root / ".venv")], check=True)
    say("installing / updating Python packages (one time, several minutes)...")
    r = subprocess.run([str(py), "-m", "pip", "install", "-r", str(req)])
    if r.returncode != 0:
        fail("package installation failed (see messages above).")
    marker.write_text(str(req.stat().st_mtime))
    return py


def ensure_ollama(env: dict) -> None:
    base = env.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    if not http_ok(base + "/api/tags"):
        exe = shutil.which("ollama") or str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe")
        if not Path(exe).exists():
            fail("Ollama is not installed. Install it from ollama.com once, then start ForgeAI.exe again.")
        say("starting Ollama...")
        subprocess.Popen([exe, "serve"], creationflags=CREATE_NO_WINDOW, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        for _ in range(30):
            if http_ok(base + "/api/tags"):
                break
            time.sleep(1)
        else:
            fail(f"Ollama did not start on {base}.")
    with urllib.request.urlopen(base + "/api/tags", timeout=5) as r:
        have = {m["name"] for m in json.load(r).get("models", [])}
    for model in {env.get("LLM_MODEL", "qwen2.5:3b"), env.get("JUDGE_MODEL", "llama3.2:3b")}:
        if model in have or f"{model}:latest" in have:
            continue
        say(f"downloading model {model} (one time)...")
        req = urllib.request.Request(base + "/api/pull", data=json.dumps({"name": model}).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=3600) as r:
            last = ""
            for line in r:
                status = json.loads(line or b"{}").get("status", "")
                if status != last:
                    say(f"  {model}: {status}")
                    last = status
    say("Ollama ready.")


def main() -> None:
    os.system("title ForgeAI") if os.name == "nt" else None
    root = root_dir()
    os.chdir(root)
    say(f"ForgeAI folder: {root}")
    if not (root / ".env").exists():
        shutil.copyfile(root / ".env.example", root / ".env")
        say("created .env from .env.example. Fill in the Supabase values, or set STORAGE_BACKEND=local.")
    env = read_env(root)
    py = ensure_venv(root)
    ensure_ollama(env)
    child_env = dict(os.environ, API_BASE_URL=f"http://127.0.0.1:{API_PORT}", PYTHONUNBUFFERED="1")
    logs = root / "data" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    say("starting API and UI...")
    api = subprocess.Popen([str(py), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(API_PORT)],
                           env=child_env, stdout=open(logs / "api.log", "ab"), stderr=subprocess.STDOUT,
                           creationflags=CREATE_NO_WINDOW)
    ui = subprocess.Popen([str(py), "-m", "streamlit", "run", "frontend/Home.py", "--server.port", str(UI_PORT),
                           "--server.address", "127.0.0.1", "--server.headless", "true"],
                          env=child_env, stdout=open(logs / "ui.log", "ab"), stderr=subprocess.STDOUT,
                          creationflags=CREATE_NO_WINDOW)
    try:
        for _ in range(120):
            if api.poll() is not None or ui.poll() is not None:
                fail(f"a server stopped during start-up; see {logs}")
            if http_ok(f"http://127.0.0.1:{API_PORT}/tools") and http_ok(f"http://127.0.0.1:{UI_PORT}"):
                break
            time.sleep(1)
        else:
            fail(f"servers did not start within 2 minutes; see {logs}")
        url = f"http://127.0.0.1:{UI_PORT}"
        say(f"ForgeAI is running: {url}  (API docs: http://127.0.0.1:{API_PORT}/docs)")
        webbrowser.open(url)
        say("Keep this window open. Close it (or press Ctrl+C) to stop ForgeAI.")
        while api.poll() is None and ui.poll() is None:
            time.sleep(2)
        say(f"a server stopped unexpectedly; see {logs}")
    except KeyboardInterrupt:
        pass
    finally:
        for p in (ui, api):
            if p.poll() is None:
                p.terminate()
        say("stopped.")


if __name__ == "__main__":
    main()
