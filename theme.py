"""Shared UI styling (Aurora palette gradient + card look) for all Streamlit pages."""

from __future__ import annotations

import html
from typing import Any

import streamlit as st

from services.project_ui import clean_test_steps

_AURORA_CSS = """
<style>
[data-testid="stAppViewContainer"] {
  background: radial-gradient(1200px 600px at 10% 0%, #2A1F66 0%, transparent 60%),
              radial-gradient(900px 600px at 100% 100%, #0E5C5C 0%, transparent 55%),
              #0F1226;
}
[data-testid="stSidebar"] { background-color: #131736; }
[data-testid="stHeader"] { background: transparent; }

[data-testid="stSidebarNav"] a,
[data-testid="stSidebarNav"] a span,
[data-testid="stSidebarNavLink"],
[data-testid="stSidebarNavLink"] span,
section[data-testid="stSidebar"] nav a,
section[data-testid="stSidebar"] nav a span {
  font-size: 17px !important;
  font-weight: 600 !important;
}

div[data-testid="stExpander"] {
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.25);
  margin-bottom: 8px;
}
div[data-testid="stExpander"] summary { font-weight: 600; }

div[data-testid="stMetric"] {
  border-radius: 12px;
  padding: 12px 16px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.22);
  background: linear-gradient(135deg, rgba(26, 31, 61, 0.9) 0%, #1a1f3d 100%);
  border: 1px solid rgba(255, 255, 255, 0.08);
}

/* Gradient metric cards (render_gradient_metric) — Option 2 */
.aurora-metric {
  border-radius: 12px;
  padding: 12px 16px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
  margin-bottom: 4px;
}
.aurora-metric__label-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
}
.aurora-metric__label {
  font-size: 0.875rem;
  color: rgba(242, 243, 251, 0.78);
  line-height: 1.4;
  flex: 1;
}
.aurora-metric__help-wrap {
  position: relative;
  flex-shrink: 0;
  line-height: 1;
}
.aurora-metric__help-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.05rem;
  height: 1.05rem;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.4);
  color: rgba(242, 243, 251, 0.9);
  font-size: 0.62rem;
  font-weight: 700;
  cursor: help;
  user-select: none;
  background: rgba(0, 0, 0, 0.2);
}
.aurora-metric__help-wrap:hover .aurora-metric__help-tip,
.aurora-metric__help-wrap:focus-within .aurora-metric__help-tip {
  visibility: visible;
  opacity: 1;
}
.aurora-metric__help-tip {
  visibility: hidden;
  opacity: 0;
  position: absolute;
  right: 0;
  top: calc(100% + 6px);
  z-index: 1000;
  min-width: 10rem;
  max-width: 18rem;
  padding: 8px 10px;
  border-radius: 8px;
  background: #1a1f3d;
  border: 1px solid rgba(124, 92, 255, 0.45);
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.45);
  color: #f2f3fb;
  font-size: 0.78rem;
  font-weight: 400;
  line-height: 1.35;
  white-space: normal;
  pointer-events: none;
  transition: opacity 0.12s ease;
}
.aurora-metric__value {
  font-size: 2.25rem;
  font-weight: 600;
  color: #f2f3fb;
  line-height: 1.2;
}
.aurora-metric--purple {
  background: linear-gradient(135deg, #3d2d7a 0%, #1a1f3d 100%);
  border: 1px solid rgba(124, 92, 255, 0.45);
}
.aurora-metric--teal {
  background: linear-gradient(135deg, #0e5c5c 0%, #1a1f3d 100%);
  border: 1px solid rgba(56, 189, 248, 0.4);
}
.aurora-metric--warm {
  background: linear-gradient(135deg, #4a2d42 0%, #1a1f3d 100%);
  border: 1px solid rgba(252, 165, 165, 0.38);
}
.aurora-metric--indigo {
  background: linear-gradient(135deg, #2a1f66 0%, #1a1f3d 100%);
  border: 1px solid rgba(155, 127, 255, 0.38);
}

/* Active project context banner */
.active-project-banner {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin: 0 0 1.25rem 0;
  padding: 12px 18px;
  border-radius: 12px;
  background: linear-gradient(
    135deg,
    rgba(124, 92, 255, 0.22) 0%,
    rgba(14, 92, 92, 0.14) 55%,
    rgba(26, 31, 61, 0.85) 100%
  );
  border: 1px solid rgba(124, 92, 255, 0.5);
  box-shadow: 0 2px 14px rgba(124, 92, 255, 0.2);
}
.active-project-banner__icon {
  font-size: 1.25rem;
  line-height: 1;
}
.active-project-banner__label {
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #c4b5fd;
}
.active-project-banner__name {
  font-size: 1.2rem;
  font-weight: 700;
  color: #ffffff;
  letter-spacing: 0.01em;
}

/* Home page */
.home-welcome-hero {
  margin: 0.35rem 0 1.85rem 0;
  padding: 1.15rem 1.4rem;
  border-radius: 12px;
  background: linear-gradient(
    135deg,
    rgba(124, 92, 255, 0.2) 0%,
    rgba(14, 92, 92, 0.14) 45%,
    rgba(26, 31, 61, 0.55) 100%
  );
  border: 1px solid rgba(124, 92, 255, 0.32);
  box-shadow: 0 2px 18px rgba(124, 92, 255, 0.12);
}
.home-welcome {
  font-size: 2.1rem;
  font-weight: 700;
  line-height: 1.3;
  color: #ffffff;
  margin: 0;
  padding: 0;
  letter-spacing: 0.015em;
}
.home-welcome--accent {
  background: linear-gradient(90deg, #e9d5ff 0%, #c4b5fd 35%, #7dd3fc 70%, #f2f3fb 100%);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  color: transparent;
}
.home-welcome__subtitle {
  font-size: 1.05rem;
  font-weight: 500;
  line-height: 1.45;
  color: rgba(242, 243, 251, 0.82);
  margin: 0.65rem 0 0 0;
  padding: 0;
}
.home-demo-link {
  margin: 0 0 1.25rem 0;
}
.home-empty-state {
  text-align: center;
  margin: 1.5rem 0 1.75rem 0;
  padding: 2rem 1.75rem 1.5rem;
  border-radius: 14px;
  background: linear-gradient(
    135deg,
    rgba(26, 31, 61, 0.95) 0%,
    rgba(14, 92, 92, 0.12) 50%,
    rgba(26, 31, 61, 0.9) 100%
  );
  border: 1px solid rgba(124, 92, 255, 0.45);
  box-shadow: 0 4px 24px rgba(124, 92, 255, 0.15);
}
.home-empty-state__icon { font-size: 2.5rem; line-height: 1; margin-bottom: 0.75rem; }
.home-empty-state__title {
  font-size: 1.35rem;
  font-weight: 700;
  color: #f2f3fb;
  margin-bottom: 0.5rem;
}
.home-empty-state__text {
  font-size: 0.95rem;
  color: rgba(242, 243, 251, 0.72);
  max-width: 28rem;
  margin: 0 auto 1.25rem;
  line-height: 1.45;
}
.home-step-path {
  display: flex;
  justify-content: center;
  gap: 2.5rem;
  flex-wrap: wrap;
  margin: 0.5rem 0 1.75rem 0;
}
.home-step-path__item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.45rem;
  min-width: 7rem;
}
.home-step-path__num {
  width: 2rem;
  height: 2rem;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.85rem;
  font-weight: 700;
  border: 2px solid rgba(255, 255, 255, 0.15);
  color: rgba(242, 243, 251, 0.45);
  background: rgba(0, 0, 0, 0.2);
}
.home-step-path__item--active .home-step-path__num {
  border-color: #7c5cff;
  color: #ffffff;
  background: linear-gradient(135deg, #7c5cff 0%, #4a3580 100%);
  box-shadow: 0 0 12px rgba(124, 92, 255, 0.45);
}
.home-step-path__item--active .home-step-path__label {
  color: #c4b5fd;
  font-weight: 600;
}
.home-step-path__item--done .home-step-path__num {
  border-color: rgba(74, 222, 128, 0.55);
  color: #4ade80;
  background: rgba(74, 222, 128, 0.14);
  font-size: 0.95rem;
}
.home-step-path__item--done .home-step-path__label {
  color: rgba(242, 243, 251, 0.62);
}
.home-step-path__label {
  font-size: 0.8rem;
  color: rgba(242, 243, 251, 0.42);
  text-align: center;
}
.home-action-card {
  border-radius: 12px;
  padding: 1.1rem 1.15rem 0.85rem;
  min-height: 7.5rem;
  margin-bottom: 0.35rem;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.28);
}
.home-action-card__icon { font-size: 1.5rem; line-height: 1; margin-bottom: 0.5rem; }
.home-action-card__title {
  font-size: 1.05rem;
  font-weight: 700;
  color: #ffffff;
  margin-bottom: 0.35rem;
}
.home-action-card__sub {
  font-size: 0.8rem;
  color: rgba(242, 243, 251, 0.72);
  line-height: 1.35;
}
.home-action-card--purple {
  background: linear-gradient(160deg, #4a3580 0%, #2a1f66 55%, #1a1f3d 100%);
  border: 1px solid rgba(124, 92, 255, 0.5);
}
.home-action-card--teal {
  background: linear-gradient(160deg, #0e7c72 0%, #0a4d4a 50%, #1a1f3d 100%);
  border: 1px solid rgba(94, 234, 212, 0.4);
}
.home-action-card--indigo {
  background: linear-gradient(160deg, #3d2d7a 0%, #2a1f66 50%, #1a1f3d 100%);
  border: 1px solid rgba(155, 127, 255, 0.42);
}
.home-quick-access { margin: 0.25rem 0 1rem 0; }
.home-quick-access__label {
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: rgba(242, 243, 251, 0.55);
  margin-bottom: 0.5rem;
}
.home-api-status {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.65rem 1rem;
  border-radius: 10px;
  font-size: 0.9rem;
  margin-top: 0.5rem;
}
.home-api-status--ok {
  background: rgba(74, 222, 128, 0.12);
  border: 1px solid rgba(74, 222, 128, 0.35);
  color: #86efac;
}
.home-api-status--warn {
  background: rgba(251, 191, 36, 0.1);
  border: 1px solid rgba(251, 191, 36, 0.35);
  color: #fcd34d;
}
.home-project-helper-label {
  font-size: 1rem;
  line-height: 1.5;
  font-weight: 400;
  color: rgba(250, 250, 250, 0.98);
  margin: 0 0 0.25rem 0;
}

button[kind="primary"],
.stDownloadButton button[kind="primary"],
.stButton > button[kind="primary"] {
  border-radius: 10px;
  background-color: #7C5CFF !important;
  color: #FFFFFF !important;
  border: 1px solid #9B7FFF !important;
  font-weight: 600 !important;
}
.stDownloadButton button[kind="primary"]:hover,
.stButton > button[kind="primary"]:hover {
  background-color: #6A4DF5 !important;
  border-color: #B8A3FF !important;
  color: #FFFFFF !important;
}
.stButton > button, .stDownloadButton > button { border-radius: 10px; }

/* Library export downloads (keys lib_export_csv / lib_export_xlsx) */
.st-key-lib_export_csv button {
  border-radius: 10px !important;
  background: linear-gradient(135deg, #7c5cff 0%, #4a3580 55%, #2a1f66 100%) !important;
  color: #ffffff !important;
  border: 1px solid rgba(184, 163, 255, 0.55) !important;
  font-weight: 600 !important;
  box-shadow: 0 2px 10px rgba(124, 92, 255, 0.35) !important;
}
.st-key-lib_export_csv button:hover {
  background: linear-gradient(135deg, #8f73ff 0%, #5c45a8 55%, #3d2d7a 100%) !important;
  border-color: #c4b5fd !important;
  color: #ffffff !important;
}
.st-key-lib_export_xlsx button {
  border-radius: 10px !important;
  background: linear-gradient(135deg, #14b8a6 0%, #0e7c72 50%, #0a4d4a 100%) !important;
  color: #ffffff !important;
  border: 1px solid rgba(94, 234, 212, 0.45) !important;
  font-weight: 600 !important;
  box-shadow: 0 2px 10px rgba(14, 92, 92, 0.35) !important;
}
.st-key-lib_export_xlsx button:hover {
  background: linear-gradient(135deg, #2dd4bf 0%, #0e8a7a 50%, #0e5c5c 100%) !important;
  border-color: #7dd3fc !important;
  color: #ffffff !important;
}

/* Demo page — Open in new tab */
.st-key-demo_open_new_tab {
  margin: 0 0 1rem 0;
}
.st-key-demo_open_new_tab a,
.st-key-demo_open_new_tab [data-testid="stLinkButton"] {
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  padding: 0.55rem 1.25rem !important;
  border-radius: 10px !important;
  background: linear-gradient(
    135deg,
    #7c5cff 0%,
    #4a3580 55%,
    #2a1f66 100%
  ) !important;
  color: #ffffff !important;
  border: 1px solid rgba(184, 163, 255, 0.55) !important;
  font-weight: 600 !important;
  text-decoration: none !important;
  box-shadow: 0 2px 10px rgba(124, 92, 255, 0.35) !important;
}
.st-key-demo_open_new_tab a:hover,
.st-key-demo_open_new_tab [data-testid="stLinkButton"]:hover {
  background: linear-gradient(
    135deg,
    #8f73ff 0%,
    #5c45a8 55%,
    #3d2d7a 100%
  ) !important;
  border-color: #c4b5fd !important;
  color: #ffffff !important;
}

/* Demo page — chapter list (compact rows + Jump buttons) */
.demo-chapters-block {
  margin-top: 0.25rem;
}
div[data-testid="stHorizontalBlock"]:has([class*="st-key-demo_chapter_jump"]) {
  gap: 0.65rem !important;
  align-items: center !important;
  margin-bottom: 0.35rem !important;
  padding: 0.4rem 0.65rem !important;
  border-radius: 10px !important;
  background: rgba(26, 31, 61, 0.55) !important;
  border: 1px solid rgba(255, 255, 255, 0.06) !important;
}
div[data-testid="stHorizontalBlock"]:has([class*="st-key-demo_chapter_jump"])
  [data-testid="stMarkdownContainer"] p {
  margin: 0 !important;
  line-height: 1.35 !important;
}
.demo-chapters__time {
  font-weight: 600;
  color: rgba(196, 181, 253, 0.95);
  font-variant-numeric: tabular-nums;
}
[class*="st-key-demo_chapter_jump"] {
  margin: 0 !important;
}
[class*="st-key-demo_chapter_jump"] a,
[class*="st-key-demo_chapter_jump"] [data-testid="stLinkButton"] {
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  width: 100% !important;
  min-width: 3.75rem !important;
  padding: 0.32rem 0.7rem !important;
  border-radius: 8px !important;
  background: linear-gradient(
    135deg,
    #5c45a8 0%,
    #4a3580 50%,
    #3d2d7a 100%
  ) !important;
  color: #ffffff !important;
  border: 1px solid rgba(184, 163, 255, 0.45) !important;
  font-weight: 600 !important;
  font-size: 0.8rem !important;
  text-decoration: none !important;
  box-shadow: 0 1px 6px rgba(92, 69, 168, 0.35) !important;
}
[class*="st-key-demo_chapter_jump"] a:hover,
[class*="st-key-demo_chapter_jump"] [data-testid="stLinkButton"]:hover {
  background: linear-gradient(
    135deg,
    #6d56c4 0%,
    #5c45a8 50%,
    #4a3580 100%
  ) !important;
  border-color: #c4b5fd !important;
  color: #ffffff !important;
}

/* ---------- Test case cards ---------- */
.tc-header {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin: 14px 0 4px;
}
.tc-id {
  font-family: ui-monospace, 'Cascadia Mono', 'Consolas', monospace;
  font-size: 0.85rem;
  color: rgba(242, 243, 251, 0.85);
  background: rgba(124, 92, 255, 0.12);
  border: 1px solid rgba(124, 92, 255, 0.35);
  padding: 2px 8px;
  border-radius: 6px;
}
.tc-chip {
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  padding: 3px 9px;
  border-radius: 999px;
  text-transform: uppercase;
}
.tc-positive { background: rgba(34, 197, 94, 0.15);  color: #4ADE80; border: 1px solid rgba(34, 197, 94, 0.4); }
.tc-negative { background: rgba(239, 68, 68, 0.15);  color: #FCA5A5; border: 1px solid rgba(239, 68, 68, 0.4); }
.tc-edge     { background: rgba(245, 158, 11, 0.15); color: #FBBF24; border: 1px solid rgba(245, 158, 11, 0.4); }
.tc-boundary { background: rgba(56, 189, 248, 0.15); color: #7DD3FC; border: 1px solid rgba(56, 189, 248, 0.4); }
.tc-default  { background: rgba(124, 92, 255, 0.15); color: #C4B5FD; border: 1px solid rgba(124, 92, 255, 0.4); }
.tc-title {
  font-size: 1.1rem;
  font-weight: 700;
  color: #F2F3FB;
  line-height: 1.3;
}
.tc-history {
  font-size: 0.75rem;
  color: #C4B5FD;
  background: rgba(124, 92, 255, 0.1);
  border: 1px solid rgba(124, 92, 255, 0.3);
  padding: 2px 8px;
  border-radius: 999px;
}
.tc-section-label {
  font-size: 0.78rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin: 12px 0 2px;
}
.tc-precond { color: #FBBF24; }
.tc-steps   { color: #7DD3FC; }
.tc-expect  { color: #4ADE80; }
</style>
"""


def apply_theme() -> None:
    """Inject Aurora palette styling. Call once at the top of every page."""
    st.markdown(_AURORA_CSS, unsafe_allow_html=True)


def render_back_to_home_link() -> None:
    """Sidebar-style escape hatch when users land on a sub-page and need Home."""
    st.page_link("Home.py", label="Back to Home", icon="🏠")


def render_active_project_banner(project_name: str) -> None:
    """Highlighted active project context (name stands out on busy pages)."""
    safe_name = html.escape(project_name)
    st.markdown(
        '<div class="active-project-banner">'
        '<span class="active-project-banner__icon">📁</span>'
        '<span class="active-project-banner__label">Active project</span>'
        f'<span class="active-project-banner__name">{safe_name}</span>'
        "</div>",
        unsafe_allow_html=True,
    )


def render_demo_chapters(
    *,
    video_url: str,
    chapters: tuple[tuple[str, int, str], ...],
) -> None:
    """Compact chapter list with Jump links (new tab) beside each title."""
    st.subheader("Chapters")
    st.caption("Jump opens the video in a new tab at that timestamp.")
    st.markdown('<div class="demo-chapters-block"></div>', unsafe_allow_html=True)

    _pad, block, _pad2 = st.columns([0.35, 7, 0.35])
    with block:
        for i, (time_label, seconds, title) in enumerate(chapters):
            time_col, title_col, jump_col = st.columns(
                [0.85, 3.35, 0.8], gap="small", vertical_alignment="center"
            )
            with time_col:
                safe_time = html.escape(time_label)
                st.markdown(
                    f'<span class="demo-chapters__time">{safe_time}</span>',
                    unsafe_allow_html=True,
                )
            with title_col:
                st.markdown(html.escape(title))
            with jump_col:
                st.link_button(
                    "Jump",
                    f"{video_url}#t={seconds}",
                    key=f"demo_chapter_jump_{i}",
                    help=f"Open at {time_label} — {title}",
                )


def render_home_demo_link(*, enabled: bool = True) -> None:
    """One-line entry to the dedicated Demo page (keeps Home uncluttered)."""
    if not enabled:
        return
    st.markdown('<div class="home-demo-link">', unsafe_allow_html=True)
    st.page_link(
        "pages/Demo.py",
        label="Watch the 8‑min Workflow Demo →",
        icon="🎬",
    )
    st.markdown("</div>", unsafe_allow_html=True)


def render_home_welcome(
    message: str,
    *,
    accent: bool = False,
    subtitle: str | None = None,
) -> None:
    """Hero welcome band under the page title (~2.1rem, stands out from cards)."""
    safe = html.escape(message)
    cls = "home-welcome home-welcome--accent" if accent else "home-welcome"
    sub_block = ""
    if subtitle:
        safe_sub = html.escape(subtitle)
        sub_block = f'<p class="home-welcome__subtitle">{safe_sub}</p>'
    st.markdown(
        f'<div class="home-welcome-hero"><p class="{cls}">{safe}</p>{sub_block}</div>',
        unsafe_allow_html=True,
    )


def render_home_your_path(
    *,
    active_step: int | None = 1,
    completed_steps: set[int] | None = None,
) -> None:
    """Your path label + 3-step checklist."""
    st.markdown(
        '<div class="home-quick-access">'
        '<div class="home-quick-access__label">Your path</div></div>',
        unsafe_allow_html=True,
    )
    render_home_step_path(active_step=active_step, completed_steps=completed_steps)


def render_home_empty_state() -> None:
    """First-visit card when no workspace exists yet."""
    st.markdown(
        '<div class="home-empty-state">'
        '<div class="home-empty-state__icon">📁</div>'
        '<div class="home-empty-state__title">You don\'t have a workspace yet</div>'
        '<div class="home-empty-state__text">'
        "Create one to store requirements, tests, and bugs for a product or release."
        "</div></div>",
        unsafe_allow_html=True,
    )
    _c1, _c2, _c3 = st.columns([1, 2, 1])
    with _c2:
        st.page_link(
            "pages/Settings.py",
            label="Create your first project →",
            icon="➕",
            use_container_width=True,
        )


def render_home_step_path(
    *,
    active_step: int | None = 1,
    completed_steps: set[int] | None = None,
) -> None:
    """Three-step onboarding path (done, active, or upcoming)."""
    steps = [
        (1, "Set up workspace"),
        (2, "Import context (optional)"),
        (3, "Generate tests"),
    ]
    done = completed_steps or set()
    items: list[str] = []
    for num, label in steps:
        classes: list[str] = []
        if num in done:
            classes.append("home-step-path__item--done")
        if active_step is not None and num == active_step:
            classes.append("home-step-path__item--active")
        cls = " ".join(classes)
        safe_label = html.escape(label)
        badge = "✓" if num in done else str(num)
        items.append(
            f'<div class="home-step-path__item {cls}">'
            f'<span class="home-step-path__num">{badge}</span>'
            f'<span class="home-step-path__label">{safe_label}</span>'
            "</div>"
        )
    st.markdown(
        f'<div class="home-step-path">{"".join(items)}</div>',
        unsafe_allow_html=True,
    )


def render_home_action_card(
    variant: str,
    icon: str,
    title: str,
    subtitle: str,
    page: str,
    *,
    link_label: str = "Open →",
) -> None:
    """Gradient action card with navigation link (purple, teal, or indigo)."""
    safe_title = html.escape(title)
    safe_sub = html.escape(subtitle)
    safe_icon = html.escape(icon)
    st.markdown(
        f'<div class="home-action-card home-action-card--{variant}">'
        f'<div class="home-action-card__icon">{safe_icon}</div>'
        f'<div class="home-action-card__title">{safe_title}</div>'
        f'<div class="home-action-card__sub">{safe_sub}</div>'
        "</div>",
        unsafe_allow_html=True,
    )
    st.page_link(page, label=link_label, use_container_width=True)


def render_home_api_status(*, banner_message: str | None) -> None:
    """API readiness strip on Home; uses the same message as the global banner."""
    if banner_message is None:
        st.markdown(
            '<div class="home-api-status home-api-status--ok">'
            '<span>✅</span><span>Ready to generate</span></div>',
            unsafe_allow_html=True,
        )
        return
    st.warning(banner_message)


def render_gradient_metric(
    label: str,
    value: Any,
    variant: str = "purple",
    *,
    help: str | None = None,
) -> None:
    """Metric card with reliable gradient styling (purple, teal, warm, indigo)."""
    safe_label = html.escape(label)
    safe_value = html.escape(str(value))
    if help:
        safe_help = html.escape(help)
        help_block = (
            '<span class="aurora-metric__help-wrap">'
            f'<span class="aurora-metric__help-icon" tabindex="0" '
            f'role="button" aria-label="Help: {safe_label}">?</span>'
            f'<span class="aurora-metric__help-tip" role="tooltip">{safe_help}</span>'
            "</span>"
        )
        label_block = (
            f'<div class="aurora-metric__label-row">'
            f'<span class="aurora-metric__label">{safe_label}</span>'
            f"{help_block}</div>"
        )
    else:
        label_block = f'<div class="aurora-metric__label">{safe_label}</div>'
    st.markdown(
        f'<div class="aurora-metric aurora-metric--{variant}">'
        f"{label_block}"
        f'<div class="aurora-metric__value">{safe_value}</div>'
        f"</div>",
        unsafe_allow_html=True,
    )


def render_test_case_card(case: dict[str, Any], *, history_linked: bool = False) -> None:
    """Readable test case body (matches Generate page card styling)."""
    test_type = (case.get("test_type") or "").strip().lower()
    chip_class = {
        "positive": "tc-positive",
        "negative": "tc-negative",
        "edge": "tc-edge",
        "boundary": "tc-boundary",
    }.get(test_type, "tc-default")
    chip_label = html.escape((case.get("test_type") or "test").upper())
    tc_id = html.escape(str(case.get("testcase_id") or "—"))
    title = html.escape(str(case.get("title") or ""))
    history_html = (
        '<span class="tc-history">✨ history linked</span>' if history_linked else ""
    )

    st.markdown(
        f'<div class="tc-header">'
        f'<span class="tc-id">{tc_id}</span>'
        f'<span class="tc-chip {chip_class}">{chip_label}</span>'
        f'<span class="tc-title">{title}</span>'
        f"{history_html}</div>",
        unsafe_allow_html=True,
    )

    if case.get("description"):
        st.markdown(case["description"])

    if case.get("preconditions"):
        st.markdown(
            '<div class="tc-section-label tc-precond">📌 Preconditions</div>',
            unsafe_allow_html=True,
        )
        st.markdown(case["preconditions"])

    step_list = clean_test_steps(case.get("steps"))
    if step_list:
        st.markdown(
            '<div class="tc-section-label tc-steps">📝 Test steps</div>',
            unsafe_allow_html=True,
        )
        for idx, step in enumerate(step_list, start=1):
            st.markdown(f"{idx}. {step}")

    if case.get("expected_result"):
        st.markdown(
            '<div class="tc-section-label tc-expect">🎯 Expected result</div>',
            unsafe_allow_html=True,
        )
        st.markdown(case["expected_result"])


def scroll_to_anchor(anchor_id: str) -> None:
    """Smooth-scroll the app view to an element id (Streamlit parent document)."""
    safe_id = html.escape(anchor_id, quote=True)
    st.components.v1.html(
        f"""<script>
        (function() {{
          const doc = window.parent.document;
          const el = doc.getElementById("{safe_id}");
          if (el) el.scrollIntoView({{ behavior: "smooth", block: "start" }});
        }})();
        </script>""",
        height=0,
    )


def render_library_case_detail(case: dict[str, Any]) -> None:
    """Library detail panel: card + metadata, no embeddings or raw JSON."""
    render_test_case_card(case)

    parts: list[str] = []
    if case.get("linked_requirement"):
        parts.append(f"**Requirement:** `{case['linked_requirement']}`")
    if case.get("module"):
        parts.append(f"**Module:** {case['module']}")
    parts.append(f"**Priority:** {case.get('priority') or '—'}")
    parts.append(f"**Source:** {case.get('source') or '—'}")
    if case.get("is_duplicate"):
        dup = case.get("similar_to_title") or "another case"
        parts.append(f"**Duplicate:** yes (similar to {dup})")
    if case.get("_similarity") is not None:
        parts.append(f"**Search similarity:** {float(case['_similarity']):.2f}")
    st.caption(" · ".join(parts))


def _severity_chip_class(severity: str) -> str:
    s = severity.strip().lower()
    if s in ("critical", "blocker", "high"):
        return "tc-negative"
    if s in ("medium", "major"):
        return "tc-edge"
    if s in ("low", "minor", "trivial"):
        return "tc-positive"
    return "tc-default"


def render_bug_report_detail(bug: dict[str, Any]) -> None:
    """Bug detail panel: readable card, no embeddings or raw JSON."""
    severity = (bug.get("severity") or "").strip()
    chip_class = _severity_chip_class(severity)
    chip_label = html.escape(severity.upper() if severity else "UNSET")
    bug_num = html.escape(str(bug.get("bug_number") or "—"))
    title = html.escape(str(bug.get("title") or ""))

    st.markdown(
        f'<div class="tc-header">'
        f'<span class="tc-id">{bug_num}</span>'
        f'<span class="tc-chip {chip_class}">{chip_label}</span>'
        f'<span class="tc-title">{title}</span>'
        f"</div>",
        unsafe_allow_html=True,
    )

    description = (bug.get("description") or "").strip()
    if description:
        st.markdown(
            '<div class="tc-section-label tc-steps">📋 Description</div>',
            unsafe_allow_html=True,
        )
        st.markdown(description)

    parts: list[str] = []
    if bug.get("component"):
        parts.append(f"**Component:** {bug['component']}")
    if bug.get("resolution"):
        parts.append(f"**Resolution:** {bug['resolution']}")
    if bug.get("created_at"):
        parts.append(f"**Created:** {bug['created_at']}")
    if parts:
        st.caption(" · ".join(parts))
