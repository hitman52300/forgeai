import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from frontend.components import api  # noqa: E402
from frontend.components.ui import kpi, page, run_picker, safe  # noqa: E402

METRICS = ["grounding", "factual_correctness", "citation_correctness", "refusal_correctness", "scope_adherence",
           "output_contract"]
page("Evaluation Dashboard", "Measured results only. Pass rate, individual metrics and the composite are reported separately.")
run = run_picker()
if not run:
    st.stop()
rid = run["run_id"]
scs = safe(api.get, f"/runs/{rid}/evaluation/scorecards") or []
if not scs:
    st.info("No evaluation has completed for this run yet.")
    st.stop()
labels = [f"iteration {s['iteration']} (v{s['agent_version']})" for s in scs]
default = next((i for i, s in enumerate(scs) if s["agent_version"] == run.get("final_agent_version")), len(scs) - 1)
pick = st.selectbox("Scorecard", labels, index=default)
sc = scs[labels.index(pick)]
c1, c2, c3, c4 = st.columns(4)
kpi(c1, "Total cases", sc["total_cases"])
kpi(c2, "Passed", sc["passed_cases"])
kpi(c3, "Failed", sc["failed_cases"])
kpi(c4, "Case pass rate", f"{sc['pass_rate']:.1%}")
st.markdown("&nbsp;")
left, right = st.columns(2)
with left:
    st.markdown("### Quality metrics")
    st.dataframe(pd.DataFrame([{"Metric": m.replace("_", " "), "Score": f"{sc['metrics'][m]:.1%}",
                                "Cases applicable": sc["metric_counts"].get(m, 0)} for m in METRICS] +
                              [{"Metric": "composite (derived)", "Score": f"{sc['composite_score']:.1%}",
                                "Cases applicable": ""}]), hide_index=True, use_container_width=True)
    st.caption(sc["composite_formula"])
with right:
    st.markdown("### Failure categories")
    if sc["failure_categories"]:
        st.bar_chart(pd.Series(sc["failure_categories"]).sort_values(), horizontal=True, color="#2F6F73")
    else:
        st.caption("No failures in this scorecard.")
    st.markdown("### By category")
    st.dataframe(pd.DataFrame([{"Category": k, "Passed": int(v["passed"]), "Total": int(v["total"]),
                                "Pass rate": f"{v['pass_rate']:.0%}"} for k, v in sc["by_category"].items()]),
                 hide_index=True, use_container_width=True)

st.markdown("### Iteration comparison")
st.line_chart(pd.DataFrame({"pass rate": [s["pass_rate"] for s in scs],
                            "composite": [s["composite_score"] for s in scs]},
                           index=[f"it{s['iteration']} v{s['agent_version']}" for s in scs]),
              color=["#2F6F73", "#9AA5B4"])
it = safe(api.get, f"/runs/{rid}/evaluation/iterations") or {}
for rec in it.get("iterations", []):
    with st.expander(f"Iteration {rec['iteration']}: v{rec['from_version']} -> v{rec.get('to_version')} · "
                     f"{rec['decision']} ({rec['decision_reason']})"):
        st.markdown(f"Pass rate {rec['score_before']:.1%} -> "
                    f"{(rec['score_after'] if rec['score_after'] is not None else float('nan')):.1%}; "
                    f"targets: {', '.join(rec['failure_categories'])}")
        st.markdown("**Changes**\n" + "\n".join(f"- {c}" for c in rec["changes_made"]) if rec["changes_made"] else "No changes")
        st.markdown("**Reasons**\n" + "\n".join(f"- {c}" for c in rec["reason_for_changes"]))
        reg = [x for x in rec["regression_results"] if x.get("now") == "fail"]
        st.markdown(f"Newly failing: {len(reg)} {[x['test_id'] for x in reg]}")

st.markdown("### Case-level results")
which = "initial" if sc["iteration"] == 0 else str(sc["iteration"])
res = safe(api.get, f"/runs/{rid}/evaluation/results/{which}") or []
ds = {c["test_id"]: c for c in (safe(api.get, f"/runs/{rid}/evaluation/dataset") or {}).get("cases", [])}
only_fail = st.toggle("Show failed cases only", value=False)
rows = [r for r in res if not only_fail or not r["passed"]]
st.dataframe(pd.DataFrame([{"Test": r["test_id"], "Category": r["category"], "Pass": "yes" if r["passed"] else "no",
                            "Refused": r["answer"]["refused"], "Failure": ", ".join(r["failure_categories"]),
                            "Question": r["question"]} for r in rows]), hide_index=True, use_container_width=True)
sel = st.selectbox("Inspect case", [r["test_id"] for r in rows]) if rows else None
if sel:
    r = next(x for x in rows if x["test_id"] == sel)
    c = ds.get(sel, {})
    a, b = st.columns(2)
    with a:
        st.markdown(f"**Question:** {r['question']}")
        st.markdown(f"**Expected behaviour:** {c.get('expected_behavior', '')}")
        st.markdown("**Expected facts:** " + ("; ".join(c.get("expected_facts", [])) or "none"))
        st.markdown(f"**Answer:** {r['answer']['answer']}")
        st.markdown(f"**Citations:** {', '.join(r['answer']['citations']) or 'none'}")
        if r["answer"]["refused"]:
            st.markdown(f"**Refusal reason:** {r['answer']['refusal_reason']}")
        if r["failure_explanation"]:
            st.error(r["failure_explanation"])
    with b:
        st.markdown("**Metric explanations**")
        for m, v in r["metrics"].items():
            st.markdown(f"- {m}: {'n/a' if not v['applicable'] else v['score']} ({v['method']}) — {v['explanation'][:220]}")
        st.markdown("**Source evidence**")
        for e in r["retrieved"]:
            st.caption(f"{e['source_filename']} ({e['location']}, sim {e['score']:.2f}): {e['excerpt'][:260]}")
