"""Shared layout: restrained enterprise styling, auth gate, status badges, run picker."""
from __future__ import annotations

import time

import streamlit as st

from frontend.components import api

CSS = """
<style>
  .block-container {padding-top: 2.2rem; max-width: 1180px;}
  h1, h2, h3 {color: #1B2A41; font-weight: 600; letter-spacing: -0.01em;}
  h1 {font-size: 1.65rem;} h2 {font-size: 1.25rem;} h3 {font-size: 1.05rem;}
  .fa-sub {color: #5B6577; font-size: 0.92rem; margin-top: -0.6rem; margin-bottom: 1.2rem;}
  .fa-card {border: 1px solid #D5D9E0; border-radius: 6px; padding: 14px 16px; background: #FFFFFF;}
  .fa-kpi {font-size: 1.6rem; font-weight: 600; color: #1B2A41;}
  .fa-kpi-l {font-size: 0.8rem; color: #5B6577; text-transform: uppercase; letter-spacing: 0.04em;}
  .fa-badge {display:inline-block; padding: 1px 8px; border-radius: 10px; font-size: 0.78rem;
             border: 1px solid #D5D9E0; background:#F4F5F7; color:#1B2A41;}
  .b-completed {background:#E7F1EF; border-color:#B9D4CF; color:#1F5450;}
  .b-running {background:#EAF0F7; border-color:#C3D3E6; color:#244A73;}
  .b-failed {background:#F8EAEA; border-color:#E3C0C0; color:#7A2E2E;}
  .b-awaiting_approval {background:#FBF3E4; border-color:#E8D3A8; color:#7A5A1E;}
  .b-pending, .b-skipped {background:#F4F5F7; color:#5B6577;}
  .fa-stage {border:1px solid #D5D9E0; border-radius:6px; padding:10px 12px; background:#fff; min-height:84px;}
  .fa-stage-t {font-size:0.82rem; font-weight:600; color:#1B2A41; margin-bottom:6px;}
  .fa-stage-m {font-size:0.74rem; color:#5B6577; margin-top:6px;}
  div[data-testid="stMetricValue"] {font-size: 1.4rem;}
  footer {visibility: hidden;}
</style>
"""

STAGE_LABELS = {"document_analysis": "Document Analysis", "interview": "Interview", "groundability": "Groundability",
                "requirements_approval": "Requirements Approval", "agent_generation": "Agent Generation",
                "evaluation_generation": "Evaluation Generation", "evaluation": "Evaluation",
                "optimization": "Optimization", "final_delivery": "Final Delivery"}


def page(title: str, subtitle: str = "") -> None:
    st.set_page_config(page_title=f"ForgeAI · {title}", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    _sidebar_auth()
    st.markdown(f"# {title}")
    if subtitle:
        st.markdown(f"<div class='fa-sub'>{subtitle}</div>", unsafe_allow_html=True)
    if api.auth_required() and not st.session_state.get("access_token"):
        st.info("Sign in from the sidebar to continue.")
        st.stop()


def _sidebar_auth() -> None:
    with st.sidebar:
        st.markdown("**ForgeAI**  \n<span style='color:#5B6577;font-size:0.85rem'>Agent engineering factory</span>",
                    unsafe_allow_html=True)
        if not api.auth_required():
            st.caption("Local mode (no authentication).")
            return
        if st.session_state.get("access_token"):
            st.caption(f"Signed in as {st.session_state.get('user_email')}")
            if st.button("Sign out"):
                st.session_state.clear()
                st.rerun()
            return
        tab_in, tab_up = st.tabs(["Sign in", "Create account"])
        with tab_in:
            with st.form("signin"):
                e = st.text_input("E-mail")
                p = st.text_input("Password", type="password")
                if st.form_submit_button("Sign in"):
                    try:
                        api.sign_in(e, p)
                        st.rerun()
                    except Exception as ex:  # noqa: BLE001
                        st.error(f"Sign-in failed: {ex}")
        with tab_up:
            with st.form("signup"):
                e = st.text_input("E-mail ")
                p = st.text_input("Password ", type="password")
                if st.form_submit_button("Create account"):
                    try:
                        st.success(api.sign_up(e, p))
                    except Exception as ex:  # noqa: BLE001
                        st.error(f"Sign-up failed: {ex}")


def badge(status: str) -> str:
    return f"<span class='fa-badge b-{status}'>{status.replace('_', ' ')}</span>"


def kpi(col, label: str, value) -> None:
    col.markdown(f"<div class='fa-card'><div class='fa-kpi-l'>{label}</div><div class='fa-kpi'>{value}</div></div>",
                 unsafe_allow_html=True)


def safe(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except api.ApiError as e:
        st.error(str(e))
        return None


def run_picker(key: str = "run", statuses: tuple[str, ...] | None = None) -> dict | None:
    runs = safe(api.get, "/runs") or []
    if statuses:
        runs = [r for r in runs if r["status"] in statuses]
    if not runs:
        st.info("No matching factory runs yet.")
        return None
    labels = {f"{r['project_name']} · {r['status']} · {r['run_id'][:8]}": r for r in runs}
    default = 0
    if st.session_state.get("current_run"):
        for i, r in enumerate(runs):
            if r["run_id"] == st.session_state["current_run"]:
                default = i
    choice = st.selectbox("Factory run", list(labels), index=default, key=key)
    r = labels[choice]
    st.session_state["current_run"] = r["run_id"]
    return r


def wait_job(job_id: str, label: str) -> dict | None:
    """Poll a background job and show its progress messages."""
    box = st.status(label, expanded=True)
    last = 0
    while True:
        j = safe(api.get, f"/jobs/{job_id}")
        if j is None:
            return None
        msgs = j["messages"]
        for m in msgs[last:] if len(msgs) >= last else msgs:
            box.write(m)
        last = len(msgs)
        if j["status"] != "running":
            if j["status"] == "completed":
                box.update(label=f"{label}: done", state="complete")
                return j["result"]
            box.update(label=f"{label}: failed", state="error")
            st.error(j["error"])
            return None
        time.sleep(2)
