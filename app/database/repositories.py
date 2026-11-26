"""Domain-level repository: the only place that knows table names.

Factory components call these methods with validated schema objects; the
backend (Supabase or local) is interchangeable.
"""
from __future__ import annotations

from typing import Any

from app.core.schemas import (AgentDefinition, ApprovalRecord, CaseResult, DocumentRecord, EvalDataset,
                              FactoryRun, IterationRecord, Scorecard, utcnow)
from app.database.supabase_client import StorageError, TableBackend, get_backend


class Repository:
    def __init__(self, backend: TableBackend | None = None):
        self.db = backend or get_backend()

    # ------------------------------------------------------------ projects
    def create_project(self, project_id: str, owner_id: str, name: str, brief: str) -> dict:
        return self.db.insert("projects", {"id": project_id, "owner_id": owner_id, "name": name, "brief": brief})

    def get_project(self, project_id: str) -> dict | None:
        rows = self.db.select("projects", {"id": project_id})
        return rows[0] if rows else None

    def list_projects(self, owner_id: str | None = None) -> list[dict]:
        return self.db.select("projects", {"owner_id": owner_id} if owner_id else None, order="-created_at")

    def assert_owner(self, project_id: str, owner_id: str) -> dict:
        p = self.get_project(project_id)
        if not p or p["owner_id"] != owner_id:
            raise PermissionError("project not found or not owned by the current user")
        return p

    def ensure_profile(self, user_id: str, display_name: str) -> None:
        if not self.db.select("profiles", {"id": user_id}):
            self.db.insert("profiles", {"id": user_id, "display_name": display_name})

    # ------------------------------------------------------------ documents
    def upsert_document(self, doc: DocumentRecord, change_type: str) -> dict:
        existing = self.db.select("documents", {"project_id": doc.project_id, "filename": doc.filename})
        meta = {"page_count": doc.page_count, "row_count": doc.row_count, "columns": doc.columns,
                "chunk_count": doc.chunk_count, "error": doc.error}
        if existing:
            row = self.db.update("documents", existing[0]["id"], {
                "current_hash": doc.content_hash, "current_version": doc.version, "size_bytes": doc.size_bytes,
                "status": doc.status, "storage_path": doc.storage_path, "metadata": meta})
        else:
            row = self.db.insert("documents", {
                "id": doc.document_id, "project_id": doc.project_id, "filename": doc.filename,
                "file_type": doc.file_type, "size_bytes": doc.size_bytes, "current_hash": doc.content_hash,
                "current_version": doc.version, "storage_path": doc.storage_path, "status": doc.status,
                "metadata": meta})
        if change_type != "unchanged":
            self.db.insert("document_versions", {
                "document_id": row["id"], "version": doc.version, "content_hash": doc.content_hash,
                "chunk_count": doc.chunk_count, "change_type": change_type, "storage_path": doc.storage_path})
        return row

    def list_documents(self, project_id: str) -> list[dict]:
        return self.db.select("documents", {"project_id": project_id}, order="filename")

    def document_versions(self, document_id: str) -> list[dict]:
        return self.db.select("document_versions", {"document_id": document_id}, order="version")

    # ------------------------------------------------------------ runs
    def create_run(self, run: FactoryRun, created_by: str | None) -> dict:
        return self.db.insert("factory_runs", {
            "id": run.run_id, "project_id": run.project_id, "status": run.status,
            "stages": {k: v.value for k, v in run.stages.items()}, "stage_messages": run.stage_messages,
            "budget": run.budget.model_dump(), "usage": run.usage.model_dump(), "created_by": created_by})

    def update_run(self, run: FactoryRun) -> None:
        self.db.update("factory_runs", run.run_id, {
            "status": run.status, "stages": {k: v.value for k, v in run.stages.items()},
            "stage_messages": run.stage_messages, "usage": run.usage.model_dump(), "budget": run.budget.model_dump(),
            "stop_reason": run.stop_reason, "final_agent_version": run.final_agent_version})

    def get_run_row(self, run_id: str) -> dict | None:
        rows = self.db.select("factory_runs", {"id": run_id})
        return rows[0] if rows else None

    def list_runs(self, project_id: str | None = None) -> list[dict]:
        return self.db.select("factory_runs", {"project_id": project_id} if project_id else None, order="-created_at")

    # ------------------------------------------------------------ interview
    def save_interview(self, run_id: str, analysis: dict, questions: list[dict]) -> dict:
        rows = self.db.select("interview_records", {"run_id": run_id})
        if rows:
            return self.db.update("interview_records", rows[0]["id"], {"analysis": analysis, "questions": questions})
        return self.db.insert("interview_records", {"run_id": run_id, "analysis": analysis, "questions": questions})

    # ------------------------------------------------------------ requirements & approvals
    def save_requirements(self, run_id: str, version: int, kind: str, content: dict,
                          groundability: dict | None, created_by: str | None) -> dict:
        return self.db.insert("requirements", {"run_id": run_id, "version": version, "kind": kind, "content": content,
                                               "groundability": groundability, "created_by": created_by})

    def list_requirements(self, run_id: str) -> list[dict]:
        return self.db.select("requirements", {"run_id": run_id}, order="version")

    def save_approval(self, rec: ApprovalRecord, requirements_id: str | None, approver_id: str | None) -> dict:
        return self.db.insert("approval_records", {
            "id": rec.approval_id, "run_id": rec.run_id, "requirements_id": requirements_id,
            "decision": rec.decision.value, "approver_id": approver_id, "approver_label": rec.approver,
            "comment": rec.comment, "diff": rec.diff, "decided_at": rec.timestamp})

    def list_approvals(self, run_id: str) -> list[dict]:
        return self.db.select("approval_records", {"run_id": run_id}, order="decided_at")

    def is_approved(self, run_id: str) -> bool:
        return any(a["decision"] == "approved" for a in self.list_approvals(run_id))

    # ------------------------------------------------------------ agents
    def create_agent(self, agent: AgentDefinition, origin: str = "forgeai") -> dict:
        return self.db.insert("agent_definitions", {
            "id": agent.agent_id, "project_id": agent.project_id, "run_id": agent.run_id,
            "agent_name": agent.agent_name, "latest_version": agent.version, "origin": origin})

    def save_agent_version(self, agent: AgentDefinition) -> dict:
        if agent.run_id and not self.is_approved(agent.run_id):
            raise PermissionError("agent generation blocked: requirements are not approved")
        row = self.db.insert("agent_versions", {
            "agent_definition_id": agent.agent_id, "version": agent.version, "parent_version": agent.parent_version,
            "definition": agent.model_dump(mode="json"), "change_summary": agent.change_summary})
        self.db.update("agent_definitions", agent.agent_id, {"latest_version": agent.version})
        return row

    def set_final_version(self, agent_id: str, version: int) -> None:
        self.db.update("agent_definitions", agent_id, {"final_version": version})

    def list_agents(self, project_id: str | None = None) -> list[dict]:
        return self.db.select("agent_definitions", {"project_id": project_id} if project_id else None,
                              order="-created_at")

    def agent_versions(self, agent_id: str) -> list[dict]:
        return self.db.select("agent_versions", {"agent_definition_id": agent_id}, order="version")

    # ------------------------------------------------------------ evaluation
    def save_dataset(self, ds: EvalDataset) -> dict[str, str]:
        self.db.insert("evaluation_datasets", {
            "id": ds.dataset_id, "run_id": ds.run_id, "version": ds.version, "case_count": len(ds.cases),
            "generation_config": ds.generation_config, "rejected_candidates": ds.rejected_candidates})
        ids = {}
        for c in ds.cases:
            row = self.db.insert("evaluation_cases", {
                "dataset_id": ds.dataset_id, "test_id": c.test_id, "category": c.category.value,
                "subtype": c.subtype, "question": c.question, "expected_behavior": c.expected_behavior,
                "expected_sources": c.expected_sources, "expected_facts": c.expected_facts,
                "must_refuse": c.must_refuse, "difficulty": c.difficulty,
                "evaluation_rationale": c.evaluation_rationale,
                "evidence": {"chunk_ids": c.evidence_chunk_ids, "fact_verification": c.fact_verification}})
            ids[c.test_id] = row["id"]
        return ids

    def save_results(self, run_id: str, results: list[CaseResult], label: str,
                     case_ids: dict[str, str] | None = None, agent_version_id: str | None = None) -> None:
        for r in results:
            row = self.db.insert("evaluation_results", {
                "run_id": run_id, "agent_version_id": agent_version_id, "agent_version": r.agent_version,
                "case_id": (case_ids or {}).get(r.test_id), "test_id": r.test_id, "iteration": r.iteration,
                "label": label, "passed": r.passed,
                "metrics": {k: v.model_dump() for k, v in r.metrics.items()},
                "answer": r.answer.model_dump(), "evidence": [e.model_dump() for e in r.retrieved],
                "deterministic_checks": r.deterministic_checks, "judge": r.judge})
            for cat in r.failure_categories:
                self.db.insert("failure_records", {"result_id": row["id"], "run_id": run_id, "category": cat.value,
                                                   "explanation": r.failure_explanation})

    def save_scorecard(self, sc: Scorecard) -> None:
        self.db.insert("scorecards", {"run_id": sc.run_id, "iteration": sc.iteration,
                                      "agent_version": sc.agent_version, "label": sc.label,
                                      "content": sc.model_dump()})

    def list_scorecards(self, run_id: str) -> list[dict]:
        return self.db.select("scorecards", {"run_id": run_id}, order="created_at")

    def save_iteration(self, run_id: str, rec: IterationRecord) -> None:
        self.db.insert("optimization_iterations", {
            "run_id": run_id, "iteration": rec.iteration, "from_version": rec.from_version,
            "to_version": rec.to_version, "score_before": rec.score_before, "score_after": rec.score_after,
            "record": rec.model_dump(), "decision": rec.decision})

    def save_change(self, run_id: str, iteration: int, version: int, field_path: str, old: Any, new: Any,
                    reason: str) -> None:
        self.db.insert("change_logs", {"run_id": run_id, "iteration": iteration, "agent_version": version,
                                       "field_path": field_path, "old_value": old, "new_value": new,
                                       "reason": reason})

    # ------------------------------------------------------------ regression / baseline
    def save_regression(self, project_id: str, base_run_id: str, changes: Any, summary: dict, report: dict) -> dict:
        return self.db.insert("regression_runs", {"project_id": project_id, "base_run_id": base_run_id,
                                                  "document_changes": changes, "summary": summary,
                                                  "report": report})

    def save_baseline(self, run_id: str, factory_version: int, name: str, results: dict) -> dict:
        return self.db.insert("baseline_comparisons", {"run_id": run_id, "factory_agent_version": factory_version,
                                                       "baseline_name": name, "results": results})

    # ------------------------------------------------------------ artifacts & audit
    def save_artifact(self, project_id: str, run_id: str | None, kind: str, filename: str, storage_path: str,
                      sha256: str, size: int) -> None:
        self.db.insert("artifacts", {"project_id": project_id, "run_id": run_id, "kind": kind, "filename": filename,
                                     "storage_path": storage_path, "sha256": sha256, "size_bytes": size})

    def list_artifacts(self, run_id: str) -> list[dict]:
        return self.db.select("artifacts", {"run_id": run_id}, order="created_at")

    def audit(self, action: str, *, project_id: str | None = None, run_id: str | None = None,
              actor_id: str | None = None, actor_label: str = "", details: dict | None = None) -> None:
        try:
            self.db.insert("audit_logs", {"action": action, "project_id": project_id, "run_id": run_id,
                                          "actor_id": actor_id, "actor_label": actor_label,
                                          "details": {**(details or {}), "at": utcnow()}})
        except StorageError:
            pass  # auditing must never crash the pipeline; failures are visible in logs

    def recent_audit(self, limit: int = 20, project_id: str | None = None) -> list[dict]:
        return self.db.select("audit_logs", {"project_id": project_id} if project_id else None,
                              order="-created_at", limit=limit)

    # ------------------------------------------------------------ tools
    def sync_tool_registry(self, specs: list[dict]) -> None:
        existing = {r["name"] for r in self.db.select("tool_registry")}
        for s in specs:
            if s["name"] not in existing:
                self.db.insert("tool_registry", s)
