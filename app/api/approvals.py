"""Human approval checkpoint (approve / reject with edits)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_factory, owned_run
from app.core.schemas import ApprovalDecision

router = APIRouter(prefix="/runs/{run_id}/approval", tags=["approvals"])


class Decision(BaseModel):
    decision: ApprovalDecision
    approver_name: str
    edits: dict[str, Any] = {}
    comment: str = ""


@router.post("")
def decide(body: Decision, ctx=Depends(owned_run)):
    run, _, user = ctx
    try:
        return get_factory().decide(run.run_id, decision=body.decision, approver=body.approver_name,
                                    approver_id=user.id if user.email != "local-operator" else None,
                                    edits=body.edits, comment=body.comment)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@router.get("/history")
def history(ctx=Depends(owned_run)):
    _, am, _ = ctx
    return am.read_json("approval_history.json") or []
