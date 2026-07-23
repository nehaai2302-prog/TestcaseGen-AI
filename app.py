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
    home_page = st.Page("pages/Home.py", title="Home", icon="🏠", url_path="home")
    demo_page = st.Page("pages/Demo.py", title="Demo", icon="🎬", url_path="demo")
    dashboard_page = st.Page(
        "pages/Dashboard.py", title="Dashboard", icon="📊", url_path="dashboard"
    )
    generate_page = st.Page(
        "pages/Generate.py", title="Generate", icon="🪄", url_path="generate"
    )
    library_page = st.Page(
        "pages/Library.py", title="Library", icon="📚", url_path="library"
    )
    trace_page = st.Page(
        "pages/Traceability.py",
        title="Traceability Matrix",
        icon="🔗",
        url_path="traceability",
    )
    bugs_page = st.Page("pages/Bugs.py", title="Bug reports", icon="🐛", url_path="bugs")
    import_page = st.Page(
        "pages/Import.py", title="Import", icon="📥", url_path="import"
    )
    settings_page = st.Page(
        "pages/Settings.py", title="Settings", icon="⚙️", url_path="settings"
    )
    logout_page = st.Page(
        "pages/Auth/Logout.py", title="Logout", icon="🚪", url_path="logout"
    )
    pages = [
        home_page,
        demo_page,
        dashboard_page,
        generate_page,
        library_page,
        trace_page,
        bugs_page,
        import_page,
        settings_page,
        logout_page,
    ]
    # Cloud-safe targets for st.page_link / switch_page (path strings can 404).
    st.session_state["_nav_pages"] = {
        "pages/Home.py": home_page,
        "pages/Demo.py": demo_page,
        "pages/Dashboard.py": dashboard_page,
        "pages/Generate.py": generate_page,
        "pages/Library.py": library_page,
        "pages/Traceability.py": trace_page,
        "pages/Bugs.py": bugs_page,
        "pages/Import.py": import_page,
        "pages/Settings.py": settings_page,
        "pages/Auth/Logout.py": logout_page,
    }
    pg = st.navigation(pages)
    if st.session_state.pop("_goto_home_after_auth", False):
        st.switch_page(home_page)
    pg.run()
else:
    login_page = st.Page(
        "pages/Auth/Login.py", title="Login", icon="🔐", url_path="login"
    )
    signup_page = st.Page(
        "pages/Auth/Signup.py", title="Sign up", icon="📝", url_path="signup"
    )
    pages = [login_page, signup_page]
    st.session_state["_nav_pages"] = {
        "pages/Auth/Login.py": login_page,
        "pages/Auth/Signup.py": signup_page,
    }
    pg = st.navigation(pages)
    if st.session_state.pop("_goto_login_after_logout", False):
        st.switch_page(login_page)
    pg.run()
