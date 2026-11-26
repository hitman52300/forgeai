import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from frontend.components import api  # noqa: E402
from frontend.components.ui import badge, page, run_picker, safe  # noqa: E402

page("Requirements Review", "Mandatory human checkpoint. Agent generation cannot start before approval.")
run = run_picker()
if not run:
    st.stop()
data = safe(api.get, f"/runs/{run['run_id']}/requirements")
if not data or not data["current"]:
    st.info("Requirements have not been generated for this run yet.")
    st.stop()
req = data["current"]
st.markdown(f"Status: {badge(run['status'])}", unsafe_allow_html=True)

tab_req, tab_ground, tab_hist = st.tabs(["Requirements", "Groundability matrix", "Approval history"])
with tab_ground:
    g = data["groundability"]["topics"]
    st.dataframe(pd.DataFrame([{"Requested topic": t["topic"], "Status": t["status"].replace("_", " "),
                                "Evidence": ", ".join(sorted({f"{e['source_filename']} ({e['location']})"
                                                             for e in t["evidence"][:3]}))
                                if t["status"] != "unsupported" else "No supporting document",
                                "Best similarity": round(t["retrieval_max_score"], 2), "Rationale": t["rationale"]}
                               for t in g]), hide_index=True, use_container_width=True)
    uns = [t["topic"] for t in g if t["status"] == "unsupported"]
    if uns:
        st.warning("Unsupported topics (the agent will refuse these): " + ", ".join(uns) +
                   ". Upload documents covering them in a new run if they are needed.")
    st.markdown("**Tool decisions**")
    for t in data.get("tool_selection") or []:
        st.markdown(f"- `{t['tool']}`: {'attached' if t['selected'] else 'not attached'} — {t['reason']}")

LIST_FIELDS = ["supported_topics", "must_answer_topics", "must_refuse_topics", "required_tools",
               "explicit_limitations", "unresolved_ambiguities", "acceptance_criteria"]
TEXT_FIELDS = ["project_name", "agent_purpose", "target_audience", "scope", "tone", "response_format"]
can_decide = run["status"] == "awaiting_approval"
with tab_req:
    st.caption("Edit any field, then approve or reject. Lists: one item per line. Knowledge sources and "
               "groundability findings are derived from the documents and are not editable.")
    with st.form("review"):
        edits = {}
        cols = st.columns(2)
        for i, f in enumerate(TEXT_FIELDS):
            box = cols[i % 2]
            v = box.text_area(f.replace("_", " ").capitalize(), req[f], height=80 if f == "scope" else 68,
                              disabled=not can_decide)
            if v != req[f]:
                edits[f] = v
        for i, f in enumerate(LIST_FIELDS):
            box = cols[i % 2]
            v = box.text_area(f.replace("_", " ").capitalize(), "\n".join(req[f]), height=120,
                              disabled=not can_decide)
            items = [x.strip() for x in v.splitlines() if x.strip()]
            if items != req[f]:
                edits[f] = items
        st.markdown("**Knowledge sources:** " + ", ".join(req["knowledge_sources"]))
        approver = st.text_input("Approver name", value=st.session_state.get("user_email", ""), disabled=not can_decide)
        comment = st.text_input("Comment", disabled=not can_decide)
        a, r = st.columns(2)
        approve = a.form_submit_button("Approve requirements", type="primary", disabled=not can_decide)
        reject = r.form_submit_button("Reject and keep editing", disabled=not can_decide)
    if edits:
        st.caption(f"Pending edits: {', '.join(edits)}")
    if approve or reject:
        if not approver.strip():
            st.error("Approver name is required.")
        else:
            res = safe(api.post, f"/runs/{run['run_id']}/approval",
                       json={"decision": "approved" if approve else "rejected", "approver_name": approver,
                             "edits": edits, "comment": comment})
            if res:
                st.success(f"{res['decision'].capitalize()} by {res['approver']} at {res['timestamp']}. "
                           f"{len(res['diff'])} field(s) changed.")
                if approve:
                    st.page_link("pages/4_Factory_Execution.py", label="Go to Factory Execution")
    if not can_decide:
        st.caption(f"Decisions are only possible while the run is awaiting approval (now: {run['status']}).")

with tab_hist:
    hist = safe(api.get, f"/runs/{run['run_id']}/approval/history") or []
    if not hist:
        st.caption("No decisions recorded yet.")
    for h in reversed(hist):
        st.markdown(f"{badge('completed' if h['decision'] == 'approved' else 'failed')} **{h['decision']}** by "
                    f"{h['approver']} · {h['timestamp'][:19]} · requirements v{h['requirements_version']}",
                    unsafe_allow_html=True)
        if h.get("comment"):
            st.caption(h["comment"])
        with st.expander(f"Version comparison ({len(h['diff'])} changed field(s))"):
            for d in h["diff"]:
                st.markdown(f"**{d['field']}**")
                if "added" in d:
                    st.markdown(f"- added: {d['added']}  \n- removed: {d['removed']}")
                else:
                    c1, c2 = st.columns(2)
                    c1.caption("Original")
                    c1.write(d["before"])
                    c2.caption("Approved")
                    c2.write(d["after"])
    vers = safe(api.get, f"/runs/{run['run_id']}/requirements/versions") or []
    if vers:
        st.markdown("**Stored requirement versions**")
        st.dataframe(pd.DataFrame([{"Version": v["version"], "Kind": v["kind"], "Created": v["created_at"][:19]}
                                   for v in vers]), hide_index=True)
