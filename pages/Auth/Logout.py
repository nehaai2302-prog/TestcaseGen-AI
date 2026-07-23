"""Sign out and clear session."""

from __future__ import annotations

import streamlit as st

from services.supabase_auth import is_authenticated, sign_out
from theme import apply_theme, safe_page_link

apply_theme()

st.title("Sign out")

if not is_authenticated():
    st.info("You are not signed in.")
    safe_page_link("pages/Auth/Login.py", label="Go to Login", icon="🔐")
    st.stop()

st.markdown(
    '<p style="font-size:1.15rem; line-height:1.5; margin:0.35rem 0 1rem 0;">'
    "This ends your session on this device. Your projects and test cases stay saved — "
    "sign back in anytime."
    "</p>",
    unsafe_allow_html=True,
)

if st.button("Sign out", type="primary", use_container_width=True):
    sign_out()
    st.session_state["_goto_login_after_logout"] = True
    st.rerun()
