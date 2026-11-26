#!/bin/sh
# Starts the API (internal, 127.0.0.1:8000) and the public Streamlit UI on $PORT (default 8501).
set -e
mkdir -p "$CHROMA_DIR" "$UPLOADS_DIR" "$ARTIFACTS_ROOT"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 &
API_PID=$!
exec python -m streamlit run frontend/Home.py --server.address 0.0.0.0 --server.port "${PORT:-8501}" \
  --server.headless true --browser.gatherUsageStats false
