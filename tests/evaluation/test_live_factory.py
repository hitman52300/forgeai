"""Live end-to-end factory run on an UNSEEN brief and corpus (real Ollama, real embeddings).

Opt-in because it takes 20-40 minutes:   set FORGEAI_LIVE=1 and run pytest on this file.
The corpus (a fictional library: TXT + DOCX) shares nothing with the two demos.
Approval inside this test is a test fixture; real runs are approved by a person.
"""
import io
import os

import httpx
import pytest

from tests.conftest import ROOT

LIVE = os.environ.get("FORGEAI_LIVE") == "1"


def _ollama_up() -> bool:
    try:
        return httpx.get("http://localhost:11434/api/tags", timeout=3).status_code == 200
    except httpx.HTTPError:
        return False


def _loans_docx() -> bytes:
    import docx
    d = docx.Document()
    d.add_heading("Borrowing rules", level=1)
    d.add_paragraph("Items can be renewed twice online if no other member has reserved them.")
    d.add_paragraph("Late returns are charged a fine per item per day; the maximum fine per item is 100 rupees.")
    t = d.add_table(rows=4, cols=3)
    for i, row in enumerate([["Item type", "Loan period", "Fine per day"], ["Book", "21 days", "2 rupees"],
                             ["DVD", "7 days", "10 rupees"], ["Magazine", "7 days", "1 rupee"]]):
        for j, v in enumerate(row):
            t.cell(i, j).text = v
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


@pytest.mark.skipif(not LIVE or not _ollama_up(), reason="set FORGEAI_LIVE=1 with Ollama running")
def test_unseen_brief_end_to_end(tmp_path, monkeypatch):
    from app.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setenv("ARTIFACTS_ROOT", str(tmp_path / "artifacts"))
    get_settings.cache_clear()
    from app.core.orchestrator import Factory
    from app.core.schemas import ApprovalDecision, BudgetLimits
    from app.database.repositories import Repository
    from app.database.supabase_client import LocalBackend

    folder = ROOT / "tests" / "fixtures" / "unseen_library"
    files = [(p.name, p.read_bytes()) for p in folder.iterdir()] + [("borrowing_rules.docx", _loans_docx())]
    brief = ("Build a help-desk assistant for members of a public library that answers questions about "
             "membership, borrowing and study room bookings. Answers must be short, friendly and based only on "
             "the library's rules; it must not make up fines or opening hours.")
    f = Factory(Repository(LocalBackend(tmp_path / "db")))
    rid = f.start(project_name="Library help desk", brief=brief, files=files, owner_id="u1", owner_label="test",
                  target_cases=15, budget=BudgetLimits(max_iterations=1))
    run, am = f.load(rid)
    qs = am.read_json("interview.json")["analysis"]["questions"]
    assert len(qs) <= 5
    if run.status == "interviewing":
        f.answer(rid, {q["question_id"]: "Use your judgement within the brief." for q in qs})
    with pytest.raises(Exception):
        f.execute(rid)  # blocked before approval
    f.decide(rid, decision=ApprovalDecision.approved, approver="test fixture", approver_id=None)
    out = f.execute(rid)
    assert out["status"] == "completed"
    ds = am.read_json("evaluation_dataset.json")
    cats = {c["category"] for c in ds["cases"]}
    assert len(ds["cases"]) >= 15 and cats == {"answerable", "out_of_scope", "edge_case"}
    sc = am.read_json("scorecards.json")
    assert sc and all(s["total_cases"] == len(ds["cases"]) for s in sc)
    for name in ("requirements.json", "groundability_report.json", "approval_record.json", "agent_definition_v1.json",
                 "agent_definition_final.json", "evaluation_results_initial.json", "evaluation_results_final.json",
                 "iteration_logs.json", "final_report.md", "final_report.pdf"):
        assert am.exists(name), name
    agent = am.read_json("agent_definition_final.json")
    assert "weather_api" not in agent["tools"]
