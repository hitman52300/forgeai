"""Reports and artifact downloads (only files inside the run's artifact folder)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.api.deps import owned_run

router = APIRouter(prefix="/runs/{run_id}/artifacts", tags=["reports"])


@router.get("")
def list_artifacts(ctx=Depends(owned_run)):
    am = ctx[1]
    return [{"name": str(p.relative_to(am.dir)).replace("\\", "/"), "size": p.stat().st_size}
            for p in sorted(am.dir.rglob("*")) if p.is_file()]


@router.get("/{name:path}")
def download(name: str, ctx=Depends(owned_run)):
    am = ctx[1]
    p = (am.dir / name).resolve()
    if am.dir.resolve() not in p.parents or not p.is_file():
        raise HTTPException(404, "artifact not found")
    return FileResponse(p, filename=p.name)
