"""ForgeAI FastAPI application.   uvicorn app.main:app --port 8000"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import agents, approvals, evaluations, factory, intake, projects, regression, reports, requirements
from app.config import get_settings
from app.core.llm_service import LLMService
from app.database.supabase_client import get_backend
from app.tools.registry import all_tools

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_app):
    _sync_tools()
    yield


app = FastAPI(title="ForgeAI", version="1.0.0", lifespan=lifespan,
              description="The agent that builds agents: intake, groundability, approval, generation, "
                          "evaluation, optimisation and delivery of document-grounded agents.")
# The Next.js frontend (e.g. on Vercel) calls the API from the browser: allow only configured origins.
_origins = [o.strip() for o in get_settings().allowed_origins.split(",") if o.strip()]
if _origins:
    app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_credentials=False,
                       allow_methods=["GET", "POST", "DELETE"], allow_headers=["Authorization", "Content-Type"])
for r in (projects, intake, requirements, approvals, factory, agents, evaluations, reports, regression):
    app.include_router(r.router)


def _sync_tools() -> None:
    try:
        from app.database.repositories import Repository
        Repository(get_backend()).sync_tool_registry([
            {"name": t.name, "description": t.description, "input_schema": t.input_model.model_json_schema(),
             "output_schema": t.output_model.model_json_schema(), "requires_network": t.requires_network,
             "permission": "network_read_only" if t.requires_network else "read_only"}
            for t in all_tools().values()])
    except Exception as e:  # noqa: BLE001
        logging.getLogger("forgeai").warning("tool registry sync skipped: %s", e)


@app.get("/health")
def health():
    s = get_settings()
    out = {"storage_backend": s.storage_backend, "llm_model": s.llm_model, "judge_model": s.judge_model}
    try:
        out["ollama"] = LLMService.from_settings(s).health()
    except Exception as e:  # noqa: BLE001
        out["ollama"] = {"ok": False, "error": str(e)}
    try:
        get_backend()
        out["database"] = "ok"
    except Exception as e:  # noqa: BLE001
        out["database"] = f"error: {e}"
    return out


@app.get("/tools")
def tools():
    return [t.spec().model_dump() for t in all_tools().values()]
