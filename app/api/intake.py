"""Intake interview."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_factory, owned_run, start_job

router = APIRouter(prefix="/runs/{run_id}/interview", tags=["intake"])


class Answers(BaseModel):
    answers: dict[str, str]


@router.get("")
def get_interview(ctx=Depends(owned_run)):
    run, am, _ = ctx
    data = am.read_json("interview.json")
    if not data:
        failed = next((run.stage_messages.get(k) for k, v in run.stages.items()
                       if getattr(v, "value", v) == "failed" and run.stage_messages.get(k)), None)
        reason = run.stop_reason or failed
        if reason:
            raise HTTPException(404, f"This run has no interview (status={run.status}): {reason}")
        raise HTTPException(
            404,
            f"This run has no interview yet (status={run.status}). If it stopped while the server "
            "was restarting, create the agent again.",
        )
    return data


@router.post("/answers")
def submit_answers(body: Answers, ctx=Depends(owned_run)):
    run, _, _ = ctx
    if run.status != "interviewing":
        raise HTTPException(409, f"run is not in the interview stage (status={run.status})")
    job = start_job("answer", run.run_id, lambda say: {"requirements": get_factory().answer(
        run.run_id, body.answers, progress=say).model_dump(mode="json")})
    return {"job_id": job.id}
