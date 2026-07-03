"""Workflow Demo video (private Supabase Storage via signed URL)."""

from __future__ import annotations

import streamlit as st

from services.bootstrap import get_repo
from theme import apply_theme, render_back_to_home_link, render_demo_chapters

# (display time, seconds, chapter title) — jumps use #t= on the signed MP4 URL
_WALKTHROUGH_CHAPTERS: tuple[tuple[str, int, str], ...] = (
    ("0:45", 45, "Project setup"),
    ("1:55", 115, "Import"),
    ("3:43", 223, "Generate"),
    ("7:25", 445, "Traceability"),
    ("8:00", 480, "Export"),
)


apply_theme()
render_back_to_home_link()

st.title("🎬 Workflow Demo")
st.caption(
    "A short (~8 min) walkthrough of the full testing workflow: set up a project, "
    "add context, generate cases, review traceability, and export."
)

try:
    repo = get_repo()
except Exception as e:
    st.error(str(e))
    st.stop()

demo_video_url = repo.get_demo_video_url()
if not demo_video_url:
    st.info(
        "Demo video is not configured. Set `DEMO_VIDEO_BUCKET` and "
        "`DEMO_VIDEO_PATH` in your environment (see `.env.example`)."
    )
    st.stop()

st.link_button(
    "Open video in new tab",
    demo_video_url,
    type="primary",
    help="Opens the signed playback URL in a new browser tab.",
)
st.video(demo_video_url)
render_demo_chapters(video_url=demo_video_url, chapters=_WALKTHROUGH_CHAPTERS)
