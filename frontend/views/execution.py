import html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st  # noqa: E402

from frontend.components import api  # noqa: E402
from frontend.components.ui import STAGE_LABELS, badge, page, run_picker, safe, wait_job  # noqa: E402

page("Factory Execution", "Stage statuses are read from the run record; a stage is shown completed only after it completed.", eyebrow="Build · Step 4")


def _short(t: str, n: int = 95) -> str:
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + " ..."


run = run_picker()
if not run:
    st.stop()
info = safe(api.get, f"/runs/{run['run_id']}")
if not info:
    st.stop()
r = info["run"]
stages = r["stages"]
msgs = r["stage_messages"]
order = list(STAGE_LABELS)
for row in (order[:5], order[5:]):
    cols = st.columns(5)
    for c, s in zip(cols, row):
        n = order.index(s) + 1
        c.markdown(f"<div class='fa-stage'><div class='fa-stage-n'>STAGE {n:02d}</div>"
                   f"<div class='fa-stage-t'>{STAGE_LABELS[s]}</div>{badge(stages[s])}"
                   f"<div class='fa-stage-m' title='{html.escape(msgs.get(s) or '', quote=True)}'>"
                   f"{html.escape(_short(msgs.get(s) or ''))}</div></div>", unsafe_allow_html=True)

st.markdown("&nbsp;")
u = r["usage"]
b = r["budget"]
c1, c2, c3, c4 = st.columns(4)
c1.metric("LLM calls", f"{u['llm_calls']} / {b['max_llm_calls']}")
c2.metric("Tokens", f"{u['prompt_tokens'] + u['completion_tokens']:,}")
c3.metric("Elapsed", f"{u['elapsed_seconds'] / 60:.1f} min")
c4.metric("Optimisation iterations", f"{u['iterations']} / {b['max_iterations']}")
if r.get("stop_reason"):
    st.info(f"Stop reason: {r['stop_reason']}")

if r["status"] == "approved":
    st.markdown("Requirements are approved. The remaining stages run unattended.")
    if st.button("Run factory (unattended)", type="primary"):
        res = safe(api.post, f"/runs/{run['run_id']}/execute")
        if res:
            out = wait_job(res["job_id"], "Running factory")
            if out:
                st.success(f"Finished: {out}")
                st.rerun()
elif r["status"] in ("awaiting_approval", "interviewing"):
    st.warning("Awaiting human approval of the requirements. Execution is blocked until then.")
    st.page_link("views/requirements.py", label="Review requirements")
elif r["status"] == "running":
    st.info("This run is executing. Refresh to update the stage statuses.")
    if st.button("Refresh"):
        st.rerun()
