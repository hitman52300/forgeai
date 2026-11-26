"""Regression mode: upload the changed document set for a completed run."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.deps import get_factory, owned_run, start_job
from app.config import get_settings
from app.regression.regression_engine import run_regression

router = APIRouter(prefix="/runs/{run_id}/regression", tags=["regression"])


@router.post("")
async def regression(files: list[UploadFile] = File(...), ctx=Depends(owned_run)):
    run, _, _ = ctx
    if run.status != "completed":
        raise HTTPException(409, "regression needs a completed run")
    s = get_settings()
    payload = [(f.filename or "unnamed", await f.read(s.max_upload_mb * 1024 * 1024 + 1)) for f in files]
    job = start_job("regression", run.run_id, lambda say: run_regression(get_factory(), run.run_id, payload,
                                                                         progress=say))
    return {"job_id": job.id}
