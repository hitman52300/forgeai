"""Shared look and feel: restrained enterprise styling, page header, badges, KPI cards, run picker."""
from __future__ import annotations

import time

import streamlit as st

from frontend.components import api

# Palette: off-white canvas, white surfaces, dark navy text, cool grey borders, one muted teal accent.
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
:root {
  --fa-bg: #F7F7F4; --fa-surface: #FFFFFF; --fa-navy: #14213D; --fa-text: #1E2A3B; --fa-muted: #5E6B7D;
  --fa-border: #E1E4E8; --fa-border-strong: #CBD1D9; --fa-accent: #2F6F73; --fa-accent-soft: #E8F1F0;
}
html, body, [class*="css"], .stMarkdown, .stTextInput, .stButton, .stSelectbox, .stTextArea {
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif !important;
}
.stApp {background: var(--fa-bg);}
.block-container {padding-top: 2.4rem; padding-bottom: 3rem; max-width: 1200px;}
h1, h2, h3, h4 {color: var(--fa-navy); letter-spacing: -0.015em;}
h1 {font-size: 1.7rem !important; font-weight: 700 !important;}
h2 {font-size: 1.2rem !important; font-weight: 600 !important;}
h3 {font-size: 1.02rem !important; font-weight: 600 !important; margin-top: 0.6rem;}
p, li, label, .stMarkdown {color: var(--fa-text);}

/* header */
.fa-eyebrow {font-size: 0.72rem; font-weight: 600; letter-spacing: 0.12em; text-transform: uppercase;
             color: var(--fa-accent); margin-bottom: 0.2rem;}
.fa-title {font-size: 1.75rem; font-weight: 700; color: var(--fa-navy); letter-spacing: -0.02em; margin: 0;}
.fa-sub {color: var(--fa-muted); font-size: 0.95rem; margin: 0.35rem 0 1.4rem 0; max-width: 760px;}
.fa-rule {height: 1px; background: var(--fa-border); margin: 0 0 1.6rem 0;}

/* surfaces */
.fa-card {border: 1px solid var(--fa-border); border-radius: 10px; padding: 16px 18px; background: var(--fa-surface);
          box-shadow: 0 1px 2px rgba(20,33,61,0.04);}
.fa-kpi-l {font-size: 0.72rem; color: var(--fa-muted); text-transform: uppercase; letter-spacing: 0.08em; font-weight: 600;}
.fa-kpi {font-size: 1.75rem; font-weight: 700; color: var(--fa-navy); margin-top: 6px; letter-spacing: -0.02em;}
.fa-kpi-n {font-size: 0.78rem; color: var(--fa-muted); margin-top: 2px;}
div[data-testid="stVerticalBlockBorderWrapper"] {border-radius: 10px !important; border-color: var(--fa-border) !important;
          background: var(--fa-surface);}

/* badges */
.fa-badge {display:inline-block; padding: 2px 10px; border-radius: 999px; font-size: 0.74rem; font-weight: 500;
           border: 1px solid var(--fa-border); background:#F3F4F6; color: var(--fa-text); white-space: nowrap;}
.b-completed {background:#E8F1EF; border-color:#C4DAD5; color:#1F5450;}
.b-running {background:#EAF0F8; border-color:#C9D7EA; color:#24476F;}
.b-failed, .b-stopped {background:#F9ECEC; border-color:#E6C7C7; color:#7A2E2E;}
.b-awaiting_approval, .b-interviewing {background:#FBF4E6; border-color:#EBD7AE; color:#7A5A1E;}
.b-pending, .b-skipped, .b-approved {background:#F3F4F6; color:var(--fa-muted);}

/* pipeline */
.fa-stage {border:1px solid var(--fa-border); border-radius:10px; padding:12px 14px; background: var(--fa-surface);
           min-height: 156px; box-shadow: 0 1px 2px rgba(20,33,61,0.03);}
.fa-stage-n {font-size:0.68rem; color: var(--fa-muted); font-weight:600; letter-spacing:0.08em;}
.fa-stage-t {font-size:0.86rem; font-weight:600; color: var(--fa-navy); margin: 2px 0 8px 0;}
.fa-stage-m {font-size:0.74rem; color: var(--fa-muted); margin-top:8px; line-height:1.35;}

/* widgets */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {
  border-radius: 8px; font-weight: 500; border: 1px solid var(--fa-border-strong); padding: 0.45rem 1rem;}
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {
  background: var(--fa-navy); border-color: var(--fa-navy); color: #fff;}
.stButton > button[kind="primary"]:hover, .stFormSubmitButton > button[kind="primary"]:hover {
  background: #22335A; border-color: #22335A;}
div[data-baseweb="input"], div[data-baseweb="textarea"], div[data-baseweb="select"] > div {border-radius: 8px !important;}
div[data-testid="stDataFrame"] {border: 1px solid var(--fa-border); border-radius: 10px;}
.stTabs [data-baseweb="tab-list"] {gap: 4px; border-bottom: 1px solid var(--fa-border);}
.stTabs [data-baseweb="tab"] {font-weight: 500;}

/* sidebar */
section[data-testid="stSidebar"] {background: #FFFFFF; border-right: 1px solid var(--fa-border);}
.fa-brand {display:flex; align-items:center; gap:10px; padding: 4px 0 14px 0;}
.fa-mark {width:32px; height:32px; border-radius:8px; background: var(--fa-navy); color:#fff; display:flex;
          align-items:center; justify-content:center; font-weight:700; font-size:0.95rem; letter-spacing:-0.03em;}
.fa-brand-t {font-weight:700; color: var(--fa-navy); font-size: 1.02rem; line-height:1.1;}
.fa-brand-s {color: var(--fa-muted); font-size: 0.74rem;}
.fa-user {font-size:0.8rem; color: var(--fa-muted); padding: 8px 10px; border:1px solid var(--fa-border);
          border-radius:8px; background:#FAFAF8; margin-bottom: 8px; overflow:hidden; text-overflow:ellipsis;}
#MainMenu, footer, [data-testid="stToolbar"] {visibility: hidden;}
</style>
"""

STAGE_LABELS = {"document_analysis": "Document Analysis", "interview": "Interview", "groundability": "Groundability",
                "requirements_approval": "Requirements Approval", "agent_generation": "Agent Generation",
                "evaluation_generation": "Evaluation Generation", "evaluation": "Evaluation",
                "optimization": "Optimization", "final_delivery": "Final Delivery"}


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def brand(sub: str = "Agent engineering factory") -> str:
    return (f"<div class='fa-brand'><div class='fa-mark'>F</div><div><div class='fa-brand-t'>ForgeAI</div>"
            f"<div class='fa-brand-s'>{sub}</div></div></div>")


def page(title: str, subtitle: str = "", eyebrow: str = "") -> None:
    """Page header. Page config, CSS, navigation and the auth gate are handled by frontend/Home.py."""
    html = ""
    if eyebrow:
        html += f"<div class='fa-eyebrow'>{eyebrow}</div>"
    html += f"<div class='fa-title'>{title}</div>"
    if subtitle:
        html += f"<div class='fa-sub'>{subtitle}</div>"
    st.markdown(html + "<div class='fa-rule'></div>", unsafe_allow_html=True)


def badge(status: str) -> str:
    return f"<span class='fa-badge b-{status}'>{status.replace('_', ' ')}</span>"


def kpi(col, label: str, value, note: str = "") -> None:
    col.markdown(f"<div class='fa-card'><div class='fa-kpi-l'>{label}</div><div class='fa-kpi'>{value}</div>"
                 f"<div class='fa-kpi-n'>{note or '&nbsp;'}</div></div>", unsafe_allow_html=True)


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
    labels = {f"{r['project_name']}  ·  {r['status'].replace('_', ' ')}  ·  {r['run_id'][:8]}": r for r in runs}
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
