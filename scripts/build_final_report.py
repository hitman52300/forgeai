"""Builds docs/FINAL_PROJECT_REPORT.md/.pdf. Every number is read from committed run artifacts.

    python scripts/build_final_report.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.reporting.pdf_exporter import markdown_to_pdf  # noqa: E402
from app.reporting.report_generator import METRIC_LABELS, pct  # noqa: E402

RUNS = ROOT / "artifacts" / "runs"
METRICS = list(METRIC_LABELS)


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def run_section(slug: str, title: str) -> list[str]:
    d = RUNS / slug
    if not (d / "scorecards.json").exists():
        return [f"### {title}", "", f"_No completed run artifacts found in `artifacts/runs/{slug}`._", ""]
    sc = load(d / "scorecards.json")
    final = load(d / "agent_definition_final.json")
    fsc = next(s for s in sc if s["agent_version"] == final["version"])
    isc = sc[0]
    ds = load(d / "evaluation_dataset.json")
    req = load(d / "requirements.json")
    appr = load(d / "approval_record.json")
    its = load(d / "iteration_logs.json") or []
    bud = load(d / "budget.json")
    ground = load(d / "groundability_report.json")
    man = load(d / "document_manifest.json")
    st = load(d / "run_state.json")["run"]
    L = [f"### {title}", "", f"**Brief.** {st['brief']}", "",
         f"**Documents:** {', '.join(x['filename'] for x in man['documents'])}.", "",
         "**Groundability matrix**", "", "| Topic | Status | Best similarity |", "|---|---|---|"]
    for t in ground["topics"]:
        L.append(f"| {t['topic']} | {t['status']} | {t['retrieval_max_score']:.2f} |")
    L += ["", f"**Requirements approved by** {appr['approver']} at {appr['timestamp'][:19]} UTC; "
          f"{len(appr['diff'])} field(s) edited during review.", "",
          f"**Agent:** {final['agent_name']}; final version v{final['version']}; tools: "
          f"{', '.join(final['tools']) or 'none'}; retrieval chunk {final['retrieval_config']['chunk_size']}/"
          f"overlap {final['retrieval_config']['chunk_overlap']}, top-k {final['retrieval_config']['top_k']}.", "",
          f"**Evaluation dataset:** {len(ds['cases'])} cases "
          f"({dict(Counter(c['category'] for c in ds['cases']))}); "
          f"{len(ds['rejected_candidates'])} generated candidates rejected by fact verification or scope checks.", "",
          "| Measure | Initial | Final |", "|---|---|---|",
          f"| Cases passed | {isc['passed_cases']}/{isc['total_cases']} | {fsc['passed_cases']}/{fsc['total_cases']} |",
          f"| Case pass rate | {pct(isc['pass_rate'])} | {pct(fsc['pass_rate'])} |"]
    for m in METRICS:
        L.append(f"| {METRIC_LABELS[m]} | {pct(isc['metrics'][m])} | {pct(fsc['metrics'][m])} |")
    L += [f"| Composite (derived) | {pct(isc['composite_score'])} | {pct(fsc['composite_score'])} |", "",
          f"**Optimisation:** {len([i for i in its if i.get('to_version')])} iteration(s); stop reason: "
          f"{st.get('stop_reason')}.", ""]
    for i in its:
        L.append(f"- Iteration {i['iteration']} (targets: {', '.join(i['failure_categories'])}): "
                 f"{pct(i['score_before'])} -> {pct(i['score_after'])}; decision {i['decision']} "
                 f"({i['decision_reason']}). Changes: {'; '.join(i['changes_made'][:4]) or 'none'}")
    L += ["", f"**Remaining failure categories (final):** {fsc['failure_categories'] or 'none'}.", "",
          f"**Budget consumed:** {bud['usage']['llm_calls']} LLM calls, {bud['total_tokens']:,} tokens, "
          f"{bud['usage']['elapsed_seconds'] / 60:.0f} minutes.", ""]
    return L


def baseline_section() -> list[str]:
    p = RUNS / "hr_demo" / "baseline_comparison" / "baseline_comparison.json"
    c = load(p)
    if not c:
        return ["_Baseline comparison artifacts not found._", ""]
    F = c["agents"]["forgeai"]["scorecard"]
    H = c["agents"]["human_baseline"]["scorecard"]
    L = ["| Measure | ForgeAI | Manual baseline |", "|---|---|---|",
         f"| Case pass rate | {pct(F['pass_rate'])} | {pct(H['pass_rate'])} |",
         f"| Failed cases | {F['failed_cases']} | {H['failed_cases']} |"]
    for m in METRICS:
        L.append(f"| {METRIC_LABELS[m]} | {pct(F['metrics'][m])} | {pct(H['metrics'][m])} |")
    L += ["", f"Balanced pairwise judgement (both orders; only consistent verdicts count): "
          f"{c['pairwise_balanced']['counts']}.", "",
          f"Creation effort. ForgeAI: {c['creation_effort']['forgeai']}. Manual: "
          f"{c['creation_effort']['human_baseline']}.", ""]
    return L


def regression_section() -> list[str]:
    regs = sorted((RUNS / "hr_demo").glob("regression_*/regression_report.json"))
    if not regs:
        return ["_No regression run artifacts found._", ""]
    s = load(regs[-1])["summary"]
    return [f"Document changes: {[(c['filename'], c['change_type']) for c in s['document_changes']]}.", "",
            f"Pass rate before the change {pct(s['pass_rate_before'])}, after {pct(s['pass_rate_after'])}. "
            f"Status counts: {s['status_counts']}. Tests whose expected facts no longer exist in the documents "
            f"(stale tests): {s['stale_tests']}. Newly failing tests attributed to the agent: "
            f"{s['agent_regressions']}.", ""]


def main() -> None:
    body = (ROOT / "docs" / "report_chapters.md").read_text(encoding="utf-8")
    body = body.replace("{{HR_RESULTS}}", "\n".join(run_section("hr_demo", "Demo 1: HR policy assistant")))
    body = body.replace("{{PROC_RESULTS}}", "\n".join(run_section("procurement_demo",
                                                                  "Demo 2: Ship-spares procurement assistant")))
    body = body.replace("{{BASELINE_RESULTS}}", "\n".join(baseline_section()))
    body = body.replace("{{REGRESSION_RESULTS}}", "\n".join(regression_section()))
    out_md = ROOT / "docs" / "FINAL_PROJECT_REPORT.md"
    out_md.write_text(body, encoding="utf-8")
    markdown_to_pdf(body, ROOT / "docs" / "FINAL_PROJECT_REPORT.pdf", title="ForgeAI - Final Project Report",
                    base_dir=ROOT / "docs")
    print("wrote", out_md, "and PDF")


if __name__ == "__main__":
    main()
