"""Factory orchestrator: drives a run through every stage and persists every artifact.

Stages: document_analysis -> interview -> groundability -> requirements_approval (human)
        -> agent_generation -> evaluation_generation -> evaluation -> optimization -> final_delivery

`start` and `answer` run up to the approval checkpoint. `execute` refuses to run
until a human approval record exists. After approval, `execute` runs unattended.
"""
from __future__ import annotations

import json
import logging
import re
import time
import traceback
from collections import Counter
from pathlib import Path
from typing import Callable

from app.config import Settings, get_settings
from app.core.budget_manager import BudgetExceeded, BudgetManager
from app.core.llm_service import LLMService
from app.core.schemas import (MIN_EVAL_CASES, AgentDefinition, ApprovalDecision, BudgetLimits, CaseResult, DocumentRecord, EvalDataset,
                              FactoryRun, GroundabilityReport, InterviewAnalysis, RequirementsDocument, RetrievalConfig,
                              Scorecard, StageStatus, ToolSelection, new_id, utcnow)
from app.database.repositories import Repository
from app.evaluation.eval_generator import EvalGenerator, GenConfig
from app.evaluation.evaluator import results_to_json
from app.factory import approval_manager
from app.factory.agent_generator import derive_retrieval_config, generate_agent
from app.factory.groundability import assess, matrix_markdown
from app.factory.interviewer import apply_answers, run_interview
from app.factory.requirements_manager import build_requirements, requirements_markdown
from app.factory.tool_selector import select_tools
from app.ingestion.pipeline import KnowledgeBase
from app.ingestion.vector_store import VectorStore, collection_name
from app.optimization.iteration_manager import run_loop
from app.reporting.artifact_manager import ArtifactManager
from app.reporting.pdf_exporter import markdown_to_pdf
from app.reporting.report_generator import final_report_md, results_csv
from app.runtime.agent_loader import save_agent
from app.tools.registry import ToolContext, all_tools

log = logging.getLogger("forgeai.orchestrator")
Progress = Callable[[str], None]


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:40] or "run"


def _index_file() -> Path:
    p = get_settings().artifacts_dir / "runs" / "_index.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _index() -> dict:
    f = _index_file()
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def _register(run_id: str, slug: str) -> None:
    idx = _index()
    idx[run_id] = slug
    _index_file().write_text(json.dumps(idx, indent=1), encoding="utf-8")


def list_run_slugs() -> dict:
    return _index()


class Factory:
    def __init__(self, repo: Repository | None = None, settings: Settings | None = None):
        self.s = settings or get_settings()
        self.repo = repo or Repository()

    # ------------------------------------------------------------------ state helpers
    def _am(self, run: FactoryRun, slug: str) -> ArtifactManager:
        return ArtifactManager(slug, run.project_id, run.run_id, self.repo)

    def load(self, run_id: str) -> tuple[FactoryRun, ArtifactManager]:
        slug = _index().get(run_id)
        project_id = ""
        if not slug:
            # not on this machine: restore from the database (stateless deployment)
            row = self.repo.get_run_row(run_id)
            if not row or not (row.get("stage_messages") or {}).get("_slug"):
                raise KeyError(f"unknown run {run_id}")
            slug, project_id = row["stage_messages"]["_slug"], row["project_id"]
            _register(run_id, slug)
        am = ArtifactManager(slug, project_id, run_id, self.repo)
        if not am.path("run_state.json").exists() and not project_id:
            row = self.repo.get_run_row(run_id)
            am.project_id = row["project_id"] if row else ""
        state = am.read_json("run_state.json")
        if state is None:
            raise KeyError(f"run state for {run_id} not found")
        run = FactoryRun.model_validate(state["run"])
        am.project_id = run.project_id
        return run, am

    def _save(self, run: FactoryRun, am: ArtifactManager) -> None:
        run.updated_at = utcnow()
        # uploaded too, so a stateless server can resume (the Storage path is overwritten in place)
        am.write_json("run_state.json", {"run": run.model_dump(mode="json"), "slug": am.slug}, kind="run_state",
                      upload=True, record=False)
        try:
            self.repo.update_run(run)
        except Exception as e:  # noqa: BLE001
            log.warning("run update not persisted to DB: %s", e)

    def _stage(self, run: FactoryRun, am: ArtifactManager, stage: str, status: StageStatus, msg: str = "") -> None:
        run.stages[stage] = status
        if msg:
            run.stage_messages[stage] = msg
        self._save(run, am)
        self.repo.audit(f"stage_{stage}_{status.value}", project_id=run.project_id, run_id=run.run_id,
                        actor_label="factory", details={"message": msg[:500]})

    def _llms(self, run: FactoryRun) -> tuple[LLMService, LLMService, BudgetManager]:
        budget = BudgetManager(run.budget, run.usage)
        agent_llm = LLMService.from_settings(self.s, budget)
        judge_llm = LLMService.from_settings(self.s, budget)
        return agent_llm, judge_llm, budget

    def _docs(self, am: ArtifactManager) -> list[DocumentRecord]:
        man = am.read_json("document_manifest.json") or {"documents": []}
        return [DocumentRecord.model_validate(d) for d in man["documents"]]

    # ------------------------------------------------------------------ stage 1-2
    def start(self, *, project_name: str, brief: str, files: list[tuple[str, bytes]], owner_id: str,
              owner_label: str, slug: str | None = None, budget: BudgetLimits | None = None,
              target_cases: int = 30, project_id: str | None = None, progress: Progress | None = None) -> str:
        say = progress or (lambda m: None)
        if not brief.strip():
            raise ValueError("a brief is required")
        project_id = project_id or new_id()
        if not self.repo.get_project(project_id):
            self.repo.create_project(project_id, owner_id, project_name, brief)
        run = FactoryRun(project_id=project_id, project_name=project_name, brief=brief, owner=owner_label,
                         budget=budget or BudgetLimits(max_llm_calls=self.s.budget_max_llm_calls,
                                                       max_tokens=self.s.budget_max_tokens,
                                                       max_iterations=self.s.budget_max_iterations,
                                                       max_seconds=self.s.budget_max_seconds,
                                                       max_eval_cases=self.s.budget_max_eval_cases))
        run.stage_messages["target_cases"] = str(min(target_cases, run.budget.max_eval_cases))
        slug = slug or f"{slugify(project_name)}_{run.run_id[:8]}"
        run.stage_messages["_slug"] = slug
        self.repo.create_run(run, owner_id)
        _register(run.run_id, slug)
        am = self._am(run, slug)
        am.write_text("input_brief.md", f"# {project_name}\n\n{brief}\n")
        self.repo.audit("run_created", project_id=project_id, run_id=run.run_id, actor_id=owner_id,
                        actor_label=owner_label, details={"files": [f[0] for f in files]})

        self._stage(run, am, "document_analysis", StageStatus.running)
        say("ingesting documents")
        base = RetrievalConfig()
        rep = KnowledgeBase(project_id, self.repo).ingest(files, base)
        am.write_json("document_manifest.json", rep.manifest() | {
            "documents": [d.model_dump() for d in rep.documents]})
        if not rep.documents:
            run.stop_reason = "no document could be ingested: " + "; ".join(rep.errors)
            self._stage(run, am, "document_analysis", StageStatus.failed, run.stop_reason)
            run.status = "failed"
            self._save(run, am)
            return run.run_id
        msg = f"{len(rep.documents)} documents ingested"
        if rep.errors:
            msg += f"; {len(rep.errors)} rejected: " + "; ".join(rep.errors)
        if rep.duplicates:
            msg += f"; duplicates skipped: {len(rep.duplicates)}"
        self._stage(run, am, "document_analysis", StageStatus.completed, msg)

        agent_llm, _, budget = self._llms(run)
        self._stage(run, am, "interview", StageStatus.running)
        say("analysing brief and documents")
        try:
            analysis, dropped = run_interview(agent_llm, brief, rep.documents, VectorStore(rep.collection))
        except Exception as e:  # noqa: BLE001
            run.usage = budget.usage
            self._stage(run, am, "interview", StageStatus.failed, f"{type(e).__name__}: {e}")
            run.status = "failed"
            self._save(run, am)
            raise
        run.usage = budget.usage
        am.write_json("interview.json", {"analysis": analysis.model_dump(), "dropped_questions": dropped,
                                         "answers": {}})
        self.repo.save_interview(run.run_id, analysis.model_dump(), [q.model_dump() for q in analysis.questions])
        run.status = "interviewing"
        self._stage(run, am, "interview", StageStatus.awaiting_approval if analysis.questions else StageStatus.completed,
                    f"{len(analysis.questions)} clarifying question(s); {len(dropped)} dropped as answered by documents")
        if not analysis.questions:
            self.answer(run.run_id, {}, progress=progress)
        return run.run_id

    def interview(self, run_id: str) -> InterviewAnalysis:
        _, am = self.load(run_id)
        return InterviewAnalysis.model_validate(am.read_json("interview.json")["analysis"])

    # ------------------------------------------------------------------ stage 3: groundability + requirements
    def answer(self, run_id: str, answers: dict[str, str], progress: Progress | None = None) -> RequirementsDocument:
        say = progress or (lambda m: None)
        run, am = self.load(run_id)
        iv = am.read_json("interview.json")
        analysis = apply_answers(InterviewAnalysis.model_validate(iv["analysis"]), answers)
        iv["analysis"], iv["answers"] = analysis.model_dump(), answers
        am.write_json("interview.json", iv)
        self.repo.save_interview(run_id, analysis.model_dump(), [q.model_dump() for q in analysis.questions])
        self._stage(run, am, "interview", StageStatus.completed,
                    f"{len(analysis.questions)} question(s), {sum(1 for q in analysis.questions if q.answer)} answered")
        docs = self._docs(am)
        store = VectorStore(collection_name(run.project_id, 800, 120))
        agent_llm, _, budget = self._llms(run)
        self._stage(run, am, "groundability", StageStatus.running)
        say("checking groundability of requested topics")
        try:
            ground = assess(agent_llm, store, analysis.requested_topics, analysis.agent_purpose)
            am.write_json("groundability_report.json", ground.model_dump())
            am.write_text("groundability_matrix.md", matrix_markdown(ground) + "\n")
            counts = Counter(t.status.value for t in ground.topics)
            self._stage(run, am, "groundability", StageStatus.completed, json.dumps(dict(counts)))
            say("selecting tools and writing requirements")
            notes = "\n".join(f"{q.question} -> {q.answer}" for q in analysis.questions if q.answer)
            ctx = ToolContext(csv_files=KnowledgeBase(run.project_id).csv_files())
            tools = select_tools(agent_llm, purpose=analysis.agent_purpose, scope=run.brief,
                                 topics=analysis.requested_topics, source_types=[d.file_type for d in docs],
                                 notes=notes, ctx=ctx)
            req = build_requirements(agent_llm, project_name=run.project_name, brief=run.brief, analysis=analysis,
                                     docs=docs, ground=ground, tools=tools, store=store)
        except Exception as e:  # noqa: BLE001
            run.usage = budget.usage
            self._stage(run, am, "groundability", StageStatus.failed, f"{type(e).__name__}: {e}")
            raise
        run.usage = budget.usage
        am.write_json("tool_selection.json", [t.model_dump() for t in tools])
        am.write_json("requirements_original.json", req.model_dump(mode="json"))
        am.write_json("requirements.json", req.model_dump(mode="json"))
        am.write_text("requirements.md", requirements_markdown(req, tools))
        existing = self.repo.list_requirements(run_id)
        self.repo.save_requirements(run_id, len(existing) + 1, "original", req.model_dump(mode="json"),
                                    ground.model_dump(mode="json"), None)
        run.status = "awaiting_approval"
        self._stage(run, am, "requirements_approval", StageStatus.awaiting_approval,
                    "requirements generated; waiting for human approval")
        return req

    def requirements(self, run_id: str) -> RequirementsDocument:
        _, am = self.load(run_id)
        return RequirementsDocument.model_validate(am.read_json("requirements.json"))

    # ------------------------------------------------------------------ stage 4: human approval
    def decide(self, run_id: str, *, decision: ApprovalDecision, approver: str, approver_id: str | None,
               edits: dict | None = None, comment: str = "") -> dict:
        run, am = self.load(run_id)
        if run.status not in ("awaiting_approval",):
            raise ValueError(f"run is not awaiting approval (status={run.status})")
        original = RequirementsDocument.model_validate(am.read_json("requirements_original.json"))
        current = RequirementsDocument.model_validate(am.read_json("requirements.json"))
        edited = approval_manager.apply_edits(current, edits or {})
        rec = approval_manager.decide(self.repo, run_id=run_id, original=original, edited=edited, decision=decision,
                                      approver=approver, approver_id=approver_id, comment=comment)
        history = am.read_json("approval_history.json") or []
        history.append(rec.model_dump(mode="json"))
        am.write_json("approval_history.json", history)
        am.write_json("requirements.json", edited.model_dump(mode="json"))
        am.write_text("requirements.md", requirements_markdown(
            edited, [ToolSelection.model_validate(t) for t in am.read_json("tool_selection.json") or []]))
        if decision == ApprovalDecision.approved:
            am.write_json("approval_record.json", rec.model_dump(mode="json"))
            run.status = "approved"
            self._stage(run, am, "requirements_approval", StageStatus.completed,
                        f"approved by {approver} at {rec.timestamp}; {len(rec.diff)} field(s) edited")
        else:
            run.status = "awaiting_approval"
            self._stage(run, am, "requirements_approval", StageStatus.awaiting_approval,
                        f"rejected by {approver}: {comment or 'no comment'}; edit and resubmit")
        return rec.model_dump(mode="json")

    # ------------------------------------------------------------------ stages 5-9 (unattended after approval)
    def execute(self, run_id: str, progress: Progress | None = None) -> dict:
        say = progress or (lambda m: None)
        run, am = self.load(run_id)
        approval_manager.require_approval(self.repo, run_id)  # hard gate
        if not am.exists("approval_record.json"):
            raise approval_manager.ApprovalRequired("no approval record saved for this run")
        req = RequirementsDocument.model_validate(am.read_json("requirements.json"))
        docs = self._docs(am)
        agent_llm, judge_llm, budget = self._llms(run)
        run.status = "running"
        self._save(run, am)
        stage = "agent_generation"
        try:
            # ---------------- agent generation
            self._stage(run, am, stage, StageStatus.running)
            say("generating agent definition")
            base_store = VectorStore(collection_name(run.project_id, 800, 120))
            rcfg = derive_retrieval_config(docs, base_store, RetrievalConfig())
            rcfg.collection_name = KnowledgeBase(run.project_id).ensure_index(rcfg)
            agent = generate_agent(agent_llm, req=req, project_id=run.project_id, run_id=run_id, retrieval=rcfg,
                                   model=self.s.llm_model)
            self._persist_version(agent, am, first=True)
            run.agent_id = agent.agent_id
            self._stage(run, am, stage, StageStatus.completed,
                        f"{agent.agent_name} v1; tools={agent.tools or 'none'}; {rcfg.rationale}")

            # ---------------- evaluation generation
            stage = "evaluation_generation"
            self._stage(run, am, stage, StageStatus.running)
            say("generating evaluation dataset")
            target = int(run.stage_messages.get("target_cases", "30"))
            gen = EvalGenerator(agent_llm, VectorStore(rcfg.collection_name), req, GenConfig(target_cases=target))
            ds = gen.generate(run_id)
            am.write_json("evaluation_dataset.json", ds.model_dump(mode="json"))
            case_ids = self.repo.save_dataset(ds)
            cats = Counter(c.category.value for c in ds.cases)
            if len(ds.cases) < MIN_EVAL_CASES:
                self._stage(run, am, stage, StageStatus.failed,
                            f"only {len(ds.cases)} valid cases generated (minimum {MIN_EVAL_CASES}); "
                            f"{len(ds.rejected_candidates)} candidates rejected")
                run.status = "failed"
                run.stop_reason = f"evaluation dataset below the {MIN_EVAL_CASES}-case minimum"
                self._save(run, am)
                return {"status": "failed", "reason": run.stop_reason}
            run.usage = budget.usage
            self._stage(run, am, stage, StageStatus.completed,
                        f"{len(ds.cases)} cases {dict(cats)}; {len(ds.rejected_candidates)} candidates rejected")

            # ---------------- evaluation + optimisation
            stage = "evaluation"
            self._stage(run, am, stage, StageStatus.running)
            versions: dict[int, AgentDefinition] = {1: agent}

            def on_version(v: AgentDefinition) -> None:
                versions[v.version] = v
                self._persist_version(v, am)

            def on_eval(it: int, res: list[CaseResult], sc: Scorecard) -> None:
                name = "evaluation_results_initial.json" if it == 0 else f"evaluation_results_iter{it}.json"
                am.write_json(name, results_to_json(res))
                self.repo.save_results(run_id, res, "factory", case_ids)
                self.repo.save_scorecard(sc)
                run.usage = budget.usage
                if it == 0:
                    self._stage(run, am, "evaluation", StageStatus.completed,
                                f"initial pass rate {sc.pass_rate:.1%} ({sc.passed_cases}/{sc.total_cases})")
                    self._stage(run, am, "optimization", StageStatus.running)
                else:
                    run.stage_messages["optimization"] = f"iteration {it}: pass rate {sc.pass_rate:.1%}"
                    self._save(run, am)

            iteration_log: list[dict] = []
            change_log: list[dict] = []

            def on_iteration(rec, changes) -> None:
                iteration_log.append(rec.model_dump())
                change_log.extend(changes)
                am.write_json("iteration_logs.json", iteration_log)
                am.write_json("change_log.json", change_log)
                self.repo.save_iteration(run_id, rec)
                for c in changes:
                    self.repo.save_change(run_id, c["iteration"], c["version"], c["field_path"], c["old"], c["new"],
                                          c["reason"])

            stage = "optimization"
            outcome = run_loop(run_id=run_id, agent=agent, req=req, dataset=ds, agent_llm=agent_llm,
                               judge_llm=judge_llm, budget=budget, quality_target=self.s.quality_target,
                               max_iterations=run.budget.max_iterations, on_version=on_version, on_eval=on_eval,
                               on_iteration=on_iteration, progress=say)
            run.usage = budget.usage
            run.stop_reason = outcome.stop_reason
            self._stage(run, am, "optimization",
                        StageStatus.completed if outcome.iterations or "target" in outcome.stop_reason
                        else StageStatus.skipped,
                        f"{len([i for i in outcome.iterations if i.to_version])} iteration(s); stop: {outcome.stop_reason}")

            # ---------------- final delivery
            stage = "final_delivery"
            self._stage(run, am, stage, StageStatus.running)
            final = versions[outcome.best_version]
            final_it = next(sc.iteration for sc in outcome.scorecards if sc.agent_version == final.version)
            final_results = outcome.results[final_it]
            self._deliver(run, am, req, ds, final, outcome, final_results, budget)
            run.final_agent_version = final.version
            run.status = "completed"
            self._stage(run, am, stage, StageStatus.completed,
                        f"final agent v{final.version}; pass rate "
                        f"{next(sc for sc in outcome.scorecards if sc.iteration == final_it).pass_rate:.1%}")
            return {"status": "completed", "final_version": final.version, "stop_reason": outcome.stop_reason}
        except BudgetExceeded as e:
            run.usage = budget.usage
            run.status = "stopped"
            run.stop_reason = f"budget exhausted: {e.reason}"
            self._stage(run, am, stage, StageStatus.failed, run.stop_reason)
            return {"status": "stopped", "reason": run.stop_reason}
        except Exception as e:  # noqa: BLE001
            run.usage = budget.usage
            run.status = "failed"
            run.stop_reason = f"{type(e).__name__}: {e}"
            self._stage(run, am, stage, StageStatus.failed, run.stop_reason)
            am.write_text("error.txt", traceback.format_exc(), upload=False)
            raise

    # ------------------------------------------------------------------ helpers
    def _persist_version(self, agent: AgentDefinition, am: ArtifactManager, first: bool = False) -> None:
        if first:
            self.repo.create_agent(agent)
        self.repo.save_agent_version(agent)
        am.write_json(f"agent_definition_v{agent.version}.json", agent.model_dump(mode="json"))
        save_agent(agent, self.s.artifacts_dir / "agents" / agent.agent_id / f"v{agent.version}.json")

    def _deliver(self, run: FactoryRun, am: ArtifactManager, req: RequirementsDocument, ds: EvalDataset,
                 final: AgentDefinition, outcome, final_results: list[CaseResult], budget: BudgetManager) -> None:
        self.repo.set_final_version(final.agent_id, final.version)
        am.write_json("agent_definition_final.json", final.model_dump(mode="json"))
        save_agent(final, self.s.artifacts_dir / "agents" / final.agent_id / "final.json")
        am.write_json("evaluation_results_final.json", results_to_json(final_results))
        am.write_text("evaluation_results_final.csv", results_csv(final_results))
        am.write_json("scorecards.json", [s.model_dump() for s in outcome.scorecards])
        am.write_json("iteration_logs.json", [i.model_dump() for i in outcome.iterations])
        am.write_json("change_log.json", outcome.change_log)
        failures = [{"iteration": it, "test_id": r.test_id, "category": r.category.value,
                     "failure_categories": [c.value for c in r.failure_categories],
                     "explanation": r.failure_explanation}
                    for it, res in outcome.results.items() for r in res if not r.passed]
        am.write_json("failure_classification.json", {
            "by_iteration": {str(it): dict(Counter(c.value for r in res if not r.passed
                                                   for c in r.failure_categories[:1]))
                             for it, res in outcome.results.items()},
            "cases": failures})
        snap = budget.snapshot()
        am.write_json("budget.json", snap)
        initial_sc = outcome.scorecards[0]
        final_sc = next(sc for sc in outcome.scorecards if sc.agent_version == final.version)
        ground = GroundabilityReport.model_validate(am.read_json("groundability_report.json"))
        md = final_report_md(project_name=run.project_name, brief=run.brief, agent=final, initial=initial_sc,
                             final=final_sc, scorecards=outcome.scorecards, iterations=outcome.iterations,
                             final_results=final_results, budget=snap, stop_reason=outcome.stop_reason,
                             groundability_md=matrix_markdown(ground), limitations=final.limitations,
                             approval=am.read_json("approval_record.json"),
                             dataset_info={"accepted": len(ds.cases), "rejected": len(ds.rejected_candidates),
                                           "categories": dict(Counter(c.category.value for c in ds.cases))})
        am.write_text("final_report.md", md)
        pdf = markdown_to_pdf(md, am.path("final_report.pdf"), title=f"ForgeAI report - {run.project_name}")
        am.write_bytes("final_report.pdf", pdf.read_bytes(), "final_report")
        am.write_json("runnable_agent.json", {
            "agent_definition": f"artifacts/agents/{final.agent_id}/final.json",
            "project_id": final.project_id, "collection": final.retrieval_config.collection_name,
            "model": final.model, "run_with": f"python scripts/run_agent.py artifacts/agents/{final.agent_id}/final.json",
            "requires": ["Ollama running with the model above", "ChromaDB index in CHROMA_DIR",
                         "raw documents in data/uploads/<project_id>"]})
