"""Streamlit sign-in page."""

from __future__ import annotations

import streamlit as st

from services.supabase_auth import AuthError, is_authenticated, sign_in
from theme import apply_theme

apply_theme()

if is_authenticated():
    st.session_state["_goto_home_after_auth"] = True
    st.rerun()

st.title("Sign in")
st.caption("Use your QAWeaver AI account to access your projects.")

with st.form("login_form"):
    email = st.text_input("Email", autocomplete="email")
    password = st.text_input("Password", type="password", autocomplete="current-password")
    submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)

if submitted:
    if not email.strip() or not password:
        st.error("Email and password are required.")
    else:
        try:
            sign_in(email, password)
            st.session_state["_goto_home_after_auth"] = True
            st.rerun()
        except AuthError as e:
            st.error(f"Sign-in failed: {e}")

st.page_link("pages/Auth/Signup.py", label="Create an account", icon="📝")
