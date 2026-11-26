import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st  # noqa: E402

from frontend.components import api  # noqa: E402
from frontend.components.ui import page, run_picker, safe, wait_job  # noqa: E402

page("Reports and Artifacts", "Every saved artifact of a run, available for download.", eyebrow="Operate")
run = run_picker()
if not run:
    st.stop()
rid = run["run_id"]
arts = safe(api.get, f"/runs/{rid}/artifacts") or []
GROUPS = {
    "Reports": ["final_report", "regression_report", "baseline"],
    "Requirements and approval": ["requirements", "groundability", "approval", "interview", "tool_selection",
                                  "input_brief", "document_manifest"],
    "Agent definitions": ["agent_definition", "runnable_agent"],
    "Evaluation": ["evaluation_dataset", "evaluation_results", "scorecards", "failure_classification"],
    "Optimisation": ["iteration_logs", "change_log", "budget"],
}
used = set()
for g, prefixes in GROUPS.items():
    items = [x for x in arts if any(Path(x["name"]).name.startswith(p) for p in prefixes) and x["name"] not in used]
    if not items:
        continue
    st.markdown(f"### {g}")
    for x in items:
        used.add(x["name"])
        c1, c2 = st.columns([4, 1])
        c1.markdown(f"`{x['name']}` · {x['size'] / 1024:.1f} KB")
        if c2.button("Prepare download", key=f"dl_{x['name']}"):
            data = safe(api.get, f"/runs/{rid}/artifacts/{x['name']}")
            if data is not None:
                payload = data if isinstance(data, bytes) else __import__("json").dumps(data, indent=2).encode()
                c2.download_button("Download", payload, file_name=Path(x["name"]).name, key=f"d2_{x['name']}")
rest = [x for x in arts if x["name"] not in used]
if rest:
    with st.expander(f"Other files ({len(rest)})"):
        for x in rest:
            st.markdown(f"`{x['name']}`")

md = next((x for x in arts if x["name"] == "final_report.md"), None)
if md:
    st.markdown("### Final report preview")
    data = safe(api.get, f"/runs/{rid}/artifacts/final_report.md")
    if data:
        st.markdown(data.decode("utf-8") if isinstance(data, bytes) else str(data))

if run["status"] == "completed":
    st.markdown("### Regression mode")
    st.caption("Upload the complete, changed document set. Previous results are kept; a new regression report is created.")
    files = st.file_uploader("Updated documents", accept_multiple_files=True, key="reg")
    if st.button("Run regression", disabled=not files):
        res = safe(api.post, f"/runs/{rid}/regression", files=[("files", (f.name, f.getvalue())) for f in files],
                   timeout=600)
        if res:
            out = wait_job(res["job_id"], "Running regression tests")
            if out:
                st.json(out)
