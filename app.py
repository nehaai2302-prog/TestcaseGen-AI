"""Streamlit navigation entrypoint."""

from __future__ import annotations

from dotenv import load_dotenv
import streamlit as st

from services.openai_errors import render_openai_key_banner
from services.session_project import restore_project_from_session

load_dotenv()
restore_project_from_session()

st.set_page_config(
    page_title="QAWeave AI",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded",
)

render_openai_key_banner()

pages = [
    st.Page("Home.py", title="Home", icon="🏠"),
    st.Page("pages/Demo.py", title="Demo", icon="🎬"),
    st.Page("pages/Dashboard.py", title="Dashboard", icon="📊"),
    st.Page("pages/Generate.py", title="Generate", icon="🪄"),
    st.Page("pages/Library.py", title="Library", icon="📚"),
    st.Page("pages/Traceability.py", title="Traceability Matrix", icon="🔗"),
    st.Page("pages/Bugs.py", title="Bug reports", icon="🐛"),
    st.Page("pages/Import.py", title="Import", icon="📥"),
    st.Page("pages/Settings.py", title="Settings", icon="⚙️"),
]

st.navigation(pages).run()
