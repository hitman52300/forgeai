"""Requirements documents and groundability."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_factory, owned_run

router = APIRouter(prefix="/runs/{run_id}/requirements", tags=["requirements"])


@router.get("")
def get_requirements(ctx=Depends(owned_run)):
    _, am, _ = ctx
    return {"current": am.read_json("requirements.json"), "original": am.read_json("requirements_original.json"),
            "tool_selection": am.read_json("tool_selection.json"),
            "groundability": am.read_json("groundability_report.json")}


@router.get("/versions")
def versions(ctx=Depends(owned_run)):
    run, _, _ = ctx
    return get_factory().repo.list_requirements(run.run_id)
