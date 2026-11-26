"""First screen: sign in or create an account (Supabase Auth)."""
import streamlit as st

from frontend.components import api
from frontend.components.ui import brand

st.markdown("""
<style>
  section[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] {display: none;}
  .block-container {max-width: 1080px; padding-top: 4.5rem;}
  .fa-hero {background: #14213D; border-radius: 14px; padding: 40px 38px; color: #E8ECF2; min-height: 470px;
            position: relative; overflow: hidden;}
  .fa-hero:after {content: ""; position: absolute; right: -90px; bottom: -90px; width: 260px; height: 260px;
                  border-radius: 50%; border: 1px solid rgba(255,255,255,0.08);}
  .fa-hero h2 {color: #FFFFFF !important; font-size: 1.65rem !important; line-height: 1.25; margin: 26px 0 10px 0;}
  .fa-hero p {color: #B9C2D0 !important; font-size: 0.95rem; line-height: 1.55;}
  .fa-hero .fa-brand-t {color: #FFFFFF;} .fa-hero .fa-brand-s {color: #9AA6B8;}
  .fa-hero .fa-mark {background: #2F6F73;}
  .fa-step {display: flex; gap: 12px; margin-top: 18px; align-items: flex-start;}
  .fa-step-n {min-width: 26px; height: 26px; border-radius: 50%; border: 1px solid rgba(255,255,255,0.25);
              color: #FFFFFF; font-size: 0.78rem; display: flex; align-items: center; justify-content: center;}
  .fa-step-t {color: #FFFFFF; font-weight: 600; font-size: 0.9rem;}
  .fa-step-d {color: #9AA6B8; font-size: 0.82rem; margin-top: 1px;}
  .fa-auth-h {font-size: 1.35rem; font-weight: 700; color: #14213D; margin: 6px 0 2px 0;}
  .fa-auth-s {color: #5E6B7D; font-size: 0.9rem; margin-bottom: 14px;}
  .fa-foot {color: #8A94A3; font-size: 0.76rem; margin-top: 14px;}
</style>
""", unsafe_allow_html=True)

left, gap, right = st.columns([1.1, 0.08, 1])
with left:
    st.markdown(
        "<div class='fa-hero'>" + brand("The agent that builds agents") +
        "<h2>Engineer document-grounded AI agents, with the evidence to trust them.</h2>"
        "<p>Describe the agent in one paragraph and upload its documents. ForgeAI scopes it, checks what the "
        "documents can support, and builds, tests and improves it after your approval.</p>"
        "<div class='fa-step'><div class='fa-step-n'>1</div><div><div class='fa-step-t'>Scope</div>"
        "<div class='fa-step-d'>Interview, groundability matrix and requirements for human approval</div></div></div>"
        "<div class='fa-step'><div class='fa-step-n'>2</div><div><div class='fa-step-t'>Build</div>"
        "<div class='fa-step-d'>Versioned agent definition, retrieval configuration and only the tools it needs</div></div></div>"
        "<div class='fa-step'><div class='fa-step-n'>3</div><div><div class='fa-step-t'>Prove</div>"
        "<div class='fa-step-d'>Verified test set, measured scorecards, targeted fixes and an honest report</div></div></div>"
        "</div>", unsafe_allow_html=True)

with right:
    with st.container(border=True):
        st.markdown("<div class='fa-auth-h'>Welcome</div>"
                    "<div class='fa-auth-s'>Sign in to your workspace or create an account.</div>",
                    unsafe_allow_html=True)
        tab_in, tab_up = st.tabs(["Sign in", "Create account"])
        with tab_in:
            with st.form("signin", border=False):
                email = st.text_input("Work e-mail", placeholder="name@company.com")
                pw = st.text_input("Password", type="password")
                go = st.form_submit_button("Sign in", type="primary", width="stretch")
            if go:
                if not email or not pw:
                    st.error("Enter your e-mail and password.")
                else:
                    try:
                        api.sign_in(email.strip(), pw)
                        st.rerun()
                    except Exception as ex:  # noqa: BLE001
                        st.error(f"Sign-in failed: {getattr(ex, 'message', None) or ex}")
        with tab_up:
            with st.form("signup", border=False):
                email2 = st.text_input("Work e-mail", placeholder="name@company.com", key="su_email")
                pw2 = st.text_input("Password", type="password", key="su_pw", help="At least 8 characters.")
                pw3 = st.text_input("Confirm password", type="password", key="su_pw2")
                go2 = st.form_submit_button("Create account", type="primary", width="stretch")
            if go2:
                if not email2 or len(pw2) < 8:
                    st.error("Enter an e-mail and a password of at least 8 characters.")
                elif pw2 != pw3:
                    st.error("The passwords do not match.")
                else:
                    try:
                        msg = api.sign_up(email2.strip(), pw2)
                        if st.session_state.get("access_token"):
                            st.rerun()
                        st.success(msg)
                    except Exception as ex:  # noqa: BLE001
                        st.error(f"Sign-up failed: {getattr(ex, 'message', None) or ex}")
        st.markdown("<div class='fa-foot'>Authentication by Supabase Auth. Each account only sees its own "
                    "projects, runs and agents.</div>", unsafe_allow_html=True)
