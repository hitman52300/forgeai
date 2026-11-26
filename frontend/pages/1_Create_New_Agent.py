import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st  # noqa: E402

from frontend.components import api  # noqa: E402
from frontend.components.ui import page, safe, wait_job  # noqa: E402

page("Create New Agent", "Describe the agent in one paragraph and upload its knowledge documents.")
allowed = api.S.allowed_extensions

with st.form("new"):
    name = st.text_input("Project name", placeholder="e.g. Customer returns assistant")
    brief = st.text_area("Brief", height=140,
                         placeholder="One paragraph: who the agent is for, what it must answer, tone, what it must not do.")
    files = st.file_uploader("Knowledge documents", accept_multiple_files=True,
                             type=[e.strip(".") for e in allowed.split(",")])
    st.caption(f"Supported file types: {allowed}. Maximum {api.S.max_upload_mb} MB per file.")
    cases = st.slider("Evaluation cases to generate", 20, 40, 30)
    go = st.form_submit_button("Start interview", type="primary")

if go:
    if not name.strip() or not brief.strip() or not files:
        st.error("Project name, brief and at least one document are required.")
    else:
        upload = [("files", (f.name, f.getvalue())) for f in files]
        res = safe(api.post, "/projects/runs", data={"name": name, "brief": brief, "target_cases": cases},
                   files=upload, timeout=600)
        if res:
            out = wait_job(res["job_id"], "Analysing documents and brief")
            if out:
                st.session_state["current_run"] = out["run_id"]
                st.success("Document analysis and interview complete. Continue on the Interview page.")
                st.page_link("pages/2_Interview.py", label="Go to Interview")
