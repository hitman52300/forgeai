"""Central configuration. All values come from environment variables / .env."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    llm_provider: str = "ollama"
    ollama_base_url: str = "http://127.0.0.1:11434"
    llm_model: str = "qwen2.5:3b"
    judge_model: str = "llama3.2:3b"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 1024
    llm_timeout_s: float = 180.0
    llm_max_retries: int = 3
    llm_seed: int = 42
    llm_num_ctx: int = 4096

    # OpenRouter (used when LLM_PROVIDER=openrouter; LLM_MODEL / JUDGE_MODEL then hold OpenRouter model ids)
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_free_only: bool = True
    openrouter_fallback_models: str = ""
    openrouter_rate_limit_retries: int = 4
    openrouter_agent_model: str = "nvidia/nemotron-3-ultra-550b-a55b:free"
    openrouter_judge_model: str = "baidu/ernie-5.5-flash-preview:free"

    @model_validator(mode="after")
    def _select_provider_models(self) -> "Settings":
        # one switch (LLM_PROVIDER) changes the models used everywhere; Ollama settings stay intact
        if self.llm_provider == "openrouter":
            self.llm_model = self.openrouter_agent_model
            self.judge_model = self.openrouter_judge_model
        return self

    @property
    def openrouter_fallback_list(self) -> list[str]:
        return [m.strip() for m in self.openrouter_fallback_models.split(",") if m.strip()]

    # embeddings / vectors
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    chroma_dir: str = "data/chroma"
    chroma_mode: str = "local"  # local | cloud
    chroma_tenant: str = ""
    chroma_database: str = ""
    chroma_api_key: str = ""

    # storage
    storage_backend: str = "supabase"
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_documents_bucket: str = "documents"
    supabase_deliverables_bucket: str = "deliverables"
    local_db_dir: str = "data/local_db"
    uploads_dir: str = "data/uploads"

    # uploads
    max_upload_mb: int = 20
    allowed_extensions: str = ".txt,.pdf,.docx,.csv"

    # budget
    budget_max_llm_calls: int = 1500
    budget_max_tokens: int = 3_000_000
    budget_max_iterations: int = 3
    budget_max_seconds: int = 10800
    budget_max_eval_cases: int = 40
    quality_target: float = Field(0.85, ge=0, le=1)

    api_base_url: str = "http://127.0.0.1:8000"
    forgeai_operator_email: str = ""

    @property
    def allowed_ext_set(self) -> set[str]:
        return {e.strip().lower() for e in self.allowed_extensions.split(",") if e.strip()}

    def path(self, rel: str) -> Path:
        p = Path(rel)
        return p if p.is_absolute() else ROOT_DIR / p

    artifacts_root: str = "artifacts"

    @property
    def artifacts_dir(self) -> Path:
        return self.path(self.artifacts_root)

    @property
    def prompts_dir(self) -> Path:
        return ROOT_DIR / "prompts"


@lru_cache
def get_settings() -> Settings:
    return Settings()
