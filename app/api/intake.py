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
    _, am, _ = ctx
    return am.read_json("interview.json")


@router.post("/answers")
def submit_answers(body: Answers, ctx=Depends(owned_run)):
    run, _, _ = ctx
    if run.status != "interviewing":
        raise HTTPException(409, f"run is not in the interview stage (status={run.status})")
    job = start_job("answer", run.run_id, lambda say: {"requirements": get_factory().answer(
        run.run_id, body.answers, progress=say).model_dump(mode="json")})
    return {"job_id": job.id}
