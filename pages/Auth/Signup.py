"""Streamlit registration page."""

from __future__ import annotations

import streamlit as st

from services.supabase_auth import AuthError, is_authenticated, sign_up
from theme import apply_theme, safe_page_link

apply_theme()

if is_authenticated():
    st.session_state["_goto_home_after_auth"] = True
    st.rerun()

st.title("Create account")
st.caption("Sign up to create projects and generate test cases.")

with st.form("signup_form"):
    first_name = st.text_input("First name", autocomplete="given-name")
    email = st.text_input("Email", autocomplete="email")
    password = st.text_input("Password", type="password", autocomplete="new-password")
    confirm = st.text_input("Confirm password", type="password", autocomplete="new-password")
    submitted = st.form_submit_button("Sign up", type="primary", use_container_width=True)

if submitted:
    if not first_name.strip():
        st.error("First name is required.")
    elif not email.strip() or not password:
        st.error("Email and password are required.")
    elif password != confirm:
        st.error("Passwords do not match.")
    elif len(password) < 6:
        st.error("Password must be at least 6 characters.")
    else:
        try:
            result = sign_up(email, password, first_name=first_name)
            if result.get("session"):
                st.session_state["_goto_home_after_auth"] = True
                st.rerun()
            else:
                st.info(
                    "Account created. Check your email to confirm your address, "
                    "then sign in."
                )
        except AuthError as e:
            st.error(f"Sign-up failed: {e}")

safe_page_link("pages/Auth/Login.py", label="Already have an account? Sign in", icon="🔐")
