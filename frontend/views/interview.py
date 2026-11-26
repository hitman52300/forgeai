import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st  # noqa: E402

from frontend.components import api  # noqa: E402
from frontend.components.ui import page, run_picker, safe, wait_job  # noqa: E402

page("Interview", "Up to five clarifying questions generated from the brief and the documents.", eyebrow="Build · Step 2")
run = run_picker()
if not run:
    st.stop()
iv = safe(api.get, f"/runs/{run['run_id']}/interview")
if not iv:
    st.stop()
a = iv["analysis"]
c1, c2 = st.columns(2)
c1.markdown(f"**Understood purpose**  \n{a['agent_purpose']}")
c1.markdown(f"**Audience**  \n{a['target_audience']}")
c2.markdown("**Requested topics**  \n" + "\n".join(f"- {t}" for t in a["requested_topics"]))
if a.get("ambiguities"):
    c2.markdown("**Ambiguities detected**  \n" + "\n".join(f"- {t}" for t in a["ambiguities"]))

qs = a["questions"]
st.markdown(f"### Clarifying questions ({len(qs)} of max 5)")
answered = sum(1 for q in qs if q.get("answer"))
st.progress(answered / len(qs) if qs else 1.0, text=f"{answered}/{len(qs)} answered")
if iv.get("dropped_questions"):
    with st.expander(f"{len(iv['dropped_questions'])} candidate question(s) dropped"):
        for d in iv["dropped_questions"]:
            st.markdown(f"- {d['question']} — *{d['reason']}* {d.get('evidence', '')}")

editable = run["status"] == "interviewing"
with st.form("answers"):
    answers = {}
    for q in qs:
        st.markdown(f"**{q['question']}**")
        if q.get("reason"):
            st.caption(q["reason"])
        answers[q["question_id"]] = st.text_area("Answer", value=q.get("answer") or "", key=q["question_id"],
                                                 label_visibility="collapsed", disabled=not editable)
    if not qs:
        st.caption("No clarification was needed.")
    sub = st.form_submit_button("Submit answers and build requirements", type="primary", disabled=not editable)
if not editable:
    st.caption(f"Run status is '{run['status']}'; answers can no longer be changed.")
if sub:
    res = safe(api.post, f"/runs/{run['run_id']}/interview/answers", json={"answers": answers})
    if res and wait_job(res["job_id"], "Checking groundability and writing requirements"):
        st.success("Requirements are ready for review.")
        st.page_link("views/requirements.py", label="Go to Requirements Review")
