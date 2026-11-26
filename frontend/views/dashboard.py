"""ForgeAI dashboard.   streamlit run frontend/Home.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from frontend.components import api  # noqa: E402
from frontend.components.ui import badge, kpi, page, safe  # noqa: E402

page("Dashboard", "Factory runs, generated agents and measured quality.", eyebrow="Overview")

runs = safe(api.get, "/runs") or []
agents = safe(api.get, "/agents") or []
health = safe(api.get, "/health") or {}

scores = []
attention = []
for r in runs:
    if r["status"] == "completed":
        sc = safe(api.get, f"/runs/{r['run_id']}/evaluation/scorecards") or []
        final = next((s for s in sc if s["agent_version"] == r.get("final_agent_version")), None)
        if final:
            scores.append(final["pass_rate"])
            if final["pass_rate"] < 0.85:
                attention.append((r, final))
    elif r["status"] in ("failed", "stopped", "awaiting_approval", "interviewing"):
        attention.append((r, None))

c1, c2, c3, c4 = st.columns(4)
kpi(c1, "Factory runs", len(runs), "all time")
kpi(c2, "Generated agents", len([a for a in agents if a.get("final_version")]))
kpi(c3, "Avg. final pass rate", f"{sum(scores) / len(scores):.0%}" if scores else "n/a")
kpi(c4, "Need attention", len(attention), "below target or awaiting input")

st.markdown("&nbsp;")
left, right = st.columns([3, 2])
with left:
    st.markdown("### Recent projects")
    if runs:
        df = pd.DataFrame([{"Project": r["project_name"], "Status": r["status"].replace("_", " "),
                            "Final version": r.get("final_agent_version") or "", "Updated": r["updated_at"][:19]}
                           for r in runs[:12]])
        st.dataframe(df, hide_index=True, width="stretch")
    else:
        st.caption("No runs yet. Start one from Create New Agent.")
    st.markdown("### Requiring attention")
    if not attention:
        st.caption("Nothing requires attention.")
    for r, sc in attention[:8]:
        why = (f"final pass rate {sc['pass_rate']:.0%} is below 85%" if sc
               else {"awaiting_approval": "requirements are waiting for approval",
                     "interviewing": "clarifying questions are waiting for answers"}.get(r["status"], r.get("stop_reason") or r["status"]))
        st.markdown(f"{badge(r['status'])} **{r['project_name']}**: {why}", unsafe_allow_html=True)
with right:
    st.markdown("### System")
    oll = health.get("ollama", {})
    st.markdown(f"- Storage backend: `{health.get('storage_backend', '?')}` ({health.get('database', '?')})\n"
                f"- Agent model: `{health.get('llm_model', '?')}`  \n- Judge model: `{health.get('judge_model', '?')}`\n"
                f"- Ollama: {'reachable' if oll.get('ok') else 'problem: ' + str(oll.get('error') or oll.get('missing'))}")
    st.markdown("### Recent activity")
    for r in runs[:6]:
        msgs = r.get("stages", {})
        last = next((k for k in reversed(list(msgs)) if msgs[k] != "pending"), None)
        if last:
            st.markdown(f"{badge(msgs[last])} {r['project_name']} · {last.replace('_', ' ')}",
                        unsafe_allow_html=True)
