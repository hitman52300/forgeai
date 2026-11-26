"""Run status and unattended execution (only after approval)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import JOBS, User, current_user, get_factory, owned_run, start_job
from app.core.orchestrator import list_run_slugs
from app.factory.approval_manager import ApprovalRequired, require_approval

router = APIRouter(tags=["factory"])


@router.get("/runs")
def list_runs(user: User = Depends(current_user)):
    f = get_factory()
    out = []
    owned = {p["id"] for p in f.repo.list_projects(user.id)}
    # runs known locally plus runs recorded in the database (a stateless server starts with no local index)
    run_ids = list(list_run_slugs())
    for pid in owned:
        run_ids += [r["id"] for r in f.repo.list_runs(pid) if r["id"] not in run_ids]
    for rid in run_ids:
        try:
            run, am = f.load(rid)
        except Exception:  # noqa: BLE001
            continue
        if run.project_id in owned:
            out.append({"run_id": rid, "slug": am.slug, **run.model_dump(mode="json", include={
                "project_name", "status", "stages", "created_at", "updated_at", "final_agent_version", "stop_reason",
                "agent_id", "project_id"})})
    return sorted(out, key=lambda r: r["created_at"], reverse=True)


@router.get("/runs/{run_id}")
def run_status(ctx=Depends(owned_run)):
    run, am, _ = ctx
    return {"run": run.model_dump(mode="json"), "slug": am.slug,
            "artifacts": sorted(p.name for p in am.dir.iterdir() if p.is_file())}


@router.post("/runs/{run_id}/execute")
def execute(ctx=Depends(owned_run)):
    run, _, _ = ctx
    f = get_factory()
    try:
        require_approval(f.repo, run.run_id)
    except ApprovalRequired as e:
        raise HTTPException(409, str(e)) from e
    if run.status not in ("approved",):
        raise HTTPException(409, f"run cannot be executed in status {run.status}")
    job = start_job("execute", run.run_id, lambda say: f.execute(run.run_id, progress=say))
    return {"job_id": job.id}


@router.get("/jobs/{job_id}")
def job_status(job_id: str, user: User = Depends(current_user)):
    j = JOBS.get(job_id)
    if not j:
        raise HTTPException(404, "job not found")
    return {"id": j.id, "kind": j.kind, "status": j.status, "messages": j.messages[-30:], "result": j.result,
            "error": j.error}
