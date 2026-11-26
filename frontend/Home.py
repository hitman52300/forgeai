"""ForgeAI UI entry point.   streamlit run frontend/Home.py

Signed-out users only see the sign-in / create-account screen. After sign-in the
application pages become available in the sidebar.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st  # noqa: E402

from frontend.components import api  # noqa: E402
from frontend.components.ui import inject_css  # noqa: E402

st.set_page_config(page_title="ForgeAI", page_icon=":material/precision_manufacturing:", layout="wide",
                   initial_sidebar_state="expanded")
inject_css()

V = "views/"
login = st.Page(V + "login.py", title="Sign in", icon=":material/login:")
signed_in = (not api.auth_required()) or bool(st.session_state.get("access_token"))

if not signed_in:
    st.navigation([login], position="hidden").run()
else:
    pages = {
        "Overview": [st.Page(V + "dashboard.py", title="Dashboard", icon=":material/space_dashboard:", default=True)],
        "Build": [
            st.Page(V + "create.py", title="Create New Agent", icon=":material/add_circle:"),
            st.Page(V + "interview.py", title="Interview", icon=":material/forum:"),
            st.Page(V + "requirements.py", title="Requirements Review", icon=":material/fact_check:"),
            st.Page(V + "execution.py", title="Factory Execution", icon=":material/account_tree:"),
        ],
        "Quality": [
            st.Page(V + "evaluation.py", title="Evaluation Dashboard", icon=":material/monitoring:"),
            st.Page(V + "studio.py", title="Agent Studio", icon=":material/tune:"),
        ],
        "Operate": [
            st.Page(V + "chat.py", title="Agent Chat", icon=":material/chat:"),
            st.Page(V + "reports.py", title="Reports and Artifacts", icon=":material/folder_open:"),
        ],
    }
    assets = Path(__file__).parent / "assets"
    st.logo(str(assets / "logo.svg"), icon_image=str(assets / "mark.svg"), size="large")
    nav = st.navigation(pages, position="sidebar")
    with st.sidebar:
        if api.auth_required():
            st.markdown(f"<div class='fa-user'>Signed in as<br><b>{st.session_state.get('user_email', '')}</b></div>",
                        unsafe_allow_html=True)
            if st.button("Sign out", icon=":material/logout:"):
                api.sign_out()
                st.rerun()
        else:
            st.caption("Local mode: authentication disabled.")
    nav.run()
