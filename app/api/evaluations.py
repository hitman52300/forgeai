"""Evaluation datasets, results and scorecards (read-only)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import owned_run

router = APIRouter(prefix="/runs/{run_id}/evaluation", tags=["evaluations"])


@router.get("/dataset")
def dataset(ctx=Depends(owned_run)):
    return ctx[1].read_json("evaluation_dataset.json")


@router.get("/scorecards")
def scorecards(ctx=Depends(owned_run)):
    return ctx[1].read_json("scorecards.json") or []


@router.get("/results/{which}")
def results(which: str, ctx=Depends(owned_run)):
    am = ctx[1]
    name = {"initial": "evaluation_results_initial.json", "final": "evaluation_results_final.json"}.get(
        which, f"evaluation_results_iter{which}.json")
    return am.read_json(name) or []


@router.get("/iterations")
def iterations(ctx=Depends(owned_run)):
    return {"iterations": ctx[1].read_json("iteration_logs.json") or [],
            "change_log": ctx[1].read_json("change_log.json") or []}
