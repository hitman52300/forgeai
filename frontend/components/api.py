"""Thin HTTP client for the ForgeAI API, plus Supabase Auth sign-in for the UI."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402

S = get_settings()
BASE = os.environ.get("API_BASE_URL", S.api_base_url)


class ApiError(RuntimeError):
    pass


def _headers() -> dict:
    tok = st.session_state.get("access_token")
    return {"Authorization": f"Bearer {tok}"} if tok else {}


def call(method: str, path: str, **kw):
    try:
        r = httpx.request(method, BASE + path, headers=_headers(), timeout=kw.pop("timeout", 120), **kw)
    except httpx.HTTPError as e:
        raise ApiError(f"API not reachable at {BASE}: {e}") from e
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail")
        except ValueError:
            detail = r.text[:300]
        raise ApiError(f"{r.status_code}: {detail}")
    ctype = r.headers.get("content-type", "")
    return r.json() if "json" in ctype else r.content


def get(path: str, **kw):
    return call("GET", path, **kw)


def post(path: str, **kw):
    return call("POST", path, **kw)


def auth_required() -> bool:
    return S.storage_backend == "supabase"


def sign_in(email: str, password: str) -> None:
    from supabase import create_client
    c = create_client(S.supabase_url, S.supabase_anon_key)
    res = c.auth.sign_in_with_password({"email": email, "password": password})
    st.session_state["access_token"] = res.session.access_token
    st.session_state["user_email"] = res.user.email


def sign_up(email: str, password: str) -> str:
    from supabase import create_client
    c = create_client(S.supabase_url, S.supabase_anon_key)
    res = c.auth.sign_up({"email": email, "password": password})
    if res.session:
        st.session_state["access_token"] = res.session.access_token
        st.session_state["user_email"] = res.user.email
        return "Account created and signed in."
    return "Account created. Confirm the e-mail sent by Supabase, then sign in."


def sign_out() -> None:
    for k in ("access_token", "user_email"):
        st.session_state.pop(k, None)
    for k in [k for k in st.session_state if k.startswith(("chat_", "sid_"))]:
        st.session_state.pop(k, None)
