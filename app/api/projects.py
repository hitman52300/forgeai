"""Projects and document upload."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.api.deps import User, current_user, get_factory, start_job
from app.config import get_settings

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("")
def list_projects(user: User = Depends(current_user)):
    return get_factory().repo.list_projects(user.id)


@router.post("/runs")
async def create_run(name: str = Form(...), brief: str = Form(...), target_cases: int = Form(30),
                     files: list[UploadFile] = File(...), user: User = Depends(current_user)):
    """Create a project + factory run: uploads documents and runs document analysis and the interview."""
    s = get_settings()
    if not files:
        raise HTTPException(400, "upload at least one document")
    payload = []
    for f in files:
        data = await f.read(s.max_upload_mb * 1024 * 1024 + 1)
        payload.append((f.filename or "unnamed", data))
    fac = get_factory()
    holder: dict = {}

    def work(say):
        rid = fac.start(project_name=name, brief=brief, files=payload, owner_id=user.id, owner_label=user.email,
                        target_cases=target_cases, progress=say)
        holder["run_id"] = rid
        return {"run_id": rid}

    job = start_job("start", f"new-{name}", work)
    return {"job_id": job.id}


@router.get("/{project_id}/documents")
def documents(project_id: str, user: User = Depends(current_user)):
    repo = get_factory().repo
    try:
        repo.assert_owner(project_id, user.id)
    except PermissionError as e:
        raise HTTPException(404, "project not found") from e
    docs = repo.list_documents(project_id)
    for d in docs:
        d["versions"] = repo.document_versions(d["id"])
    return docs
