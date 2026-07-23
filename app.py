"""Streamlit navigation entrypoint."""

from __future__ import annotations

from dotenv import load_dotenv
import streamlit as st

from services.openai_errors import render_openai_key_banner
from services.session_project import restore_project_from_session
from services.supabase_auth import init_auth_session, is_authenticated

load_dotenv(override=True)
init_auth_session()

if is_authenticated():
    restore_project_from_session()

st.set_page_config(
    page_title="QAWeaver AI",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded",
)

render_openai_key_banner()

if is_authenticated():
    home_page = st.Page("pages/Home.py", title="Home", icon="🏠")
    pages = [
        home_page,
        st.Page("pages/Demo.py", title="Demo", icon="🎬"),
        st.Page("pages/Dashboard.py", title="Dashboard", icon="📊"),
        st.Page("pages/Generate.py", title="Generate", icon="🪄"),
        st.Page("pages/Library.py", title="Library", icon="📚"),
        st.Page("pages/Traceability.py", title="Traceability Matrix", icon="🔗"),
        st.Page("pages/Bugs.py", title="Bug reports", icon="🐛"),
        st.Page("pages/Import.py", title="Import", icon="📥"),
        st.Page("pages/Settings.py", title="Settings", icon="⚙️"),
        st.Page("pages/Auth/Logout.py", title="Logout", icon="🚪"),
    ]
    pg = st.navigation(pages)
    if st.session_state.pop("_goto_home_after_auth", False):
        st.switch_page(home_page)
    pg.run()
else:
    login_page = st.Page("pages/Auth/Login.py", title="Login", icon="🔐")
    pages = [
        login_page,
        st.Page("pages/Auth/Signup.py", title="Sign up", icon="📝"),
    ]
    pg = st.navigation(pages)
    if st.session_state.pop("_goto_login_after_logout", False):
        st.switch_page(login_page)
    pg.run()
