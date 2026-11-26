# ForgeAI: API + UI in one container (online LLM via OpenRouter; no Ollama inside the image).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    HF_HOME=/data/hf STORAGE_BACKEND=supabase LLM_PROVIDER=openrouter \
    CHROMA_DIR=/data/chroma UPLOADS_DIR=/data/uploads ARTIFACTS_ROOT=/data/artifacts \
    API_BASE_URL=http://127.0.0.1:8000

WORKDIR /app
# CPU-only PyTorch keeps the image small; embeddings run on CPU.
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app ./app
COPY frontend ./frontend
COPY prompts ./prompts
COPY scripts ./scripts
COPY .streamlit ./.streamlit
COPY deploy/start.sh ./deploy/start.sh
RUN chmod +x deploy/start.sh && mkdir -p /data

# Secrets (SUPABASE_*, OPENROUTER_API_KEY) are provided as environment variables by the host, never baked in.
EXPOSE 8501
CMD ["./deploy/start.sh"]
