"""Mandatory human approval checkpoint.

The checkpoint is enforced in three places: here (`require_approval`), in the
repository (`save_agent_version` refuses unapproved runs) and in the database
(trigger on agent_versions). There is no code path that approves automatically.
"""
from __future__ import annotations

from typing import Any

from app.core.schemas import (EDITABLE_REQUIREMENT_FIELDS, ApprovalDecision, ApprovalRecord, RequirementsDocument)
from app.database.repositories import Repository


class ApprovalRequired(PermissionError):
    pass


def diff_requirements(original: dict[str, Any], edited: dict[str, Any]) -> list[dict[str, Any]]:
    changes = []
    for k in sorted(set(original) | set(edited)):
        if k == "groundability_findings":
            continue
        a, b = original.get(k), edited.get(k)
        if a == b:
            continue
        entry: dict[str, Any] = {"field": k, "before": a, "after": b}
        if isinstance(a, list) and isinstance(b, list):
            entry["added"] = [x for x in b if x not in a]
            entry["removed"] = [x for x in a if x not in b]
        changes.append(entry)
    return changes


def apply_edits(original: RequirementsDocument, edits: dict[str, Any]) -> RequirementsDocument:
    bad = [k for k in edits if k not in EDITABLE_REQUIREMENT_FIELDS]
    if bad:
        raise ValueError(f"fields not editable: {bad}")
    data = original.model_dump()
    data.update(edits)
    return RequirementsDocument.model_validate(data)  # raises if the edit makes requirements incomplete


def decide(repo: Repository, *, run_id: str, original: RequirementsDocument, edited: RequirementsDocument,
           decision: ApprovalDecision, approver: str, approver_id: str | None, comment: str = "") -> ApprovalRecord:
    if not approver.strip():
        raise ValueError("an approver name is required")
    existing = repo.list_requirements(run_id)
    version = (max((r["version"] for r in existing), default=0)) + 1
    orig_d, edit_d = original.model_dump(mode="json"), edited.model_dump(mode="json")
    diff = diff_requirements(orig_d, edit_d)
    kind = "approved" if decision == ApprovalDecision.approved else "rejected"
    req_row = repo.save_requirements(run_id, version, kind, edit_d, None, approver_id)
    rec = ApprovalRecord(run_id=run_id, decision=decision, approver=approver, comment=comment,
                         original_requirements=orig_d, approved_requirements=edit_d, diff=diff,
                         requirements_version=version)
    repo.save_approval(rec, req_row["id"], approver_id)
    repo.audit(f"requirements_{kind}", run_id=run_id, actor_id=approver_id, actor_label=approver,
               details={"version": version, "changed_fields": [d["field"] for d in diff], "comment": comment})
    return rec


def require_approval(repo: Repository, run_id: str) -> dict:
    approvals = repo.list_approvals(run_id)
    if not approvals or approvals[-1]["decision"] != "approved":
        raise ApprovalRequired("Requirements must be approved by a human before agent generation.")
    return approvals[-1]
