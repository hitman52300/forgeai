import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from frontend.components import api  # noqa: E402
from frontend.components.ui import page, safe  # noqa: E402

page("Agent Studio", "Inspect generated agent definitions and their version history.", eyebrow="Quality")
agents = safe(api.get, "/agents") or []
if not agents:
    st.info("No agents have been generated yet.")
    st.stop()
labels = {f"{a['agent_name']} · {a['project_name']} ({a['origin']})": a for a in agents}
a = labels[st.selectbox("Agent", list(labels))]
vers = safe(api.get, f"/agents/{a['id']}/versions") or []
if not vers:
    st.stop()
vnums = [v["version"] for v in vers]
default = vnums.index(a["final_version"]) if a.get("final_version") in vnums else len(vnums) - 1
v = vers[st.selectbox("Version", list(range(len(vnums))), index=default,
                      format_func=lambda i: f"v{vnums[i]}" + (" (final)" if vnums[i] == a.get("final_version") else ""))]
d = v["definition"]
c1, c2 = st.columns([2, 1])
with c1:
    st.markdown(f"### {d['agent_name']} v{d['version']}")
    st.markdown(f"**Purpose:** {d['purpose']}  \n**Audience:** {d['audience']}  \n**Tone:** {d['tone']}  \n"
                f"**Model:** `{d['model']}`")
    st.markdown("**System prompt**")
    st.code(d["system_prompt"], language="markdown")
with c2:
    st.markdown("**Retrieval configuration**")
    st.json({k: v for k, v in d["retrieval_config"].items() if k != "separators"})
    st.markdown("**Attached tools:** " + (", ".join(f"`{t}`" for t in d["tools"]) or "none"))
    st.markdown("**Output contract**")
    st.json(d["output_contract"])
    st.markdown("**Refusal policy**")
    st.json(d["refusal_policy"])
    st.markdown("**Runtime options**")
    st.json(d.get("runtime_options", {}))
st.markdown("### Version history")
st.dataframe(pd.DataFrame([{"Version": x["version"], "Parent": x["parent_version"], "Created": x["created_at"][:19],
                            "Changes": " | ".join(x["change_summary"])[:300]} for x in vers]),
             hide_index=True, width="stretch")
st.download_button("Download this definition (JSON)", json.dumps(d, indent=2),
                   file_name=f"{d['agent_name'].replace(' ', '_')}_v{d['version']}.json", mime="application/json")
