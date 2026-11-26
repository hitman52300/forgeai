import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st  # noqa: E402

from frontend.components import api  # noqa: E402
from frontend.components.ui import page, safe  # noqa: E402

page("Agent Chat Runner", "Generic runtime: any generated agent, its own knowledge base, its own history.")
agents = [a for a in (safe(api.get, "/agents") or []) if a.get("final_version") or a["origin"] == "human_baseline"]
if not agents:
    st.info("No delivered agents yet.")
    st.stop()
labels = {f"{a['agent_name']} · {a['project_name']} (v{a.get('final_version') or a['latest_version']})": a for a in agents}
a = labels[st.selectbox("Agent", list(labels))]
hist_key = f"chat_{a['id']}"  # history is per agent: never mixed across agents or projects
sid_key = f"sid_{a['id']}"
st.session_state.setdefault(hist_key, [])
st.session_state.setdefault(sid_key, str(uuid.uuid4()))
if st.button("New conversation"):
    safe(api.call, "DELETE", f"/agents/{a['id']}/chat/{st.session_state[sid_key]}")
    st.session_state[hist_key] = []
    st.session_state[sid_key] = str(uuid.uuid4())

for turn in st.session_state[hist_key]:
    with st.chat_message("user"):
        st.write(turn["q"])
    with st.chat_message("assistant"):
        r = turn["r"]
        ans = r["answer"]
        st.write(ans["answer"])
        meta = []
        if ans["citations"]:
            meta.append("Sources: " + ", ".join(ans["citations"]))
        meta.append(f"confidence {ans['confidence']:.2f}")
        st.caption(" · ".join(meta))
        if ans["refused"]:
            st.warning(f"Refused ({r['refusal_applied_by']}): {ans['refusal_reason']}")
        if not r["contract_valid"]:
            st.caption("Output contract issues: " + "; ".join(r["contract_errors"]))
        with st.expander("Citations and evidence"):
            for e in r["retrieved"]:
                st.caption(f"{e['source_filename']} ({e['location']}, similarity {e['score']:.2f})")
                st.text(e["excerpt"][:400])
            for t in r["tool_results"]:
                st.caption(f"Tool {t['tool']}: {'ok' if t['ok'] else 'error'}")
                st.json(t["output"] if t["ok"] else {"error": t["error"]})

q = st.chat_input("Ask the agent")
if q:
    with st.spinner("Retrieving evidence and generating answer"):
        r = safe(api.post, f"/agents/{a['id']}/chat", json={"question": q, "session_id": st.session_state[sid_key]},
                 timeout=300)
    if r:
        st.session_state[hist_key].append({"q": q, "r": r})
        st.rerun()
