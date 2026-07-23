"""Upload requirements and run LangGraph generation pipeline."""

from __future__ import annotations

import html
import os

import streamlit as st

from agent.exhaustiveness import (
    estimate_total_cases,
    get_profile,
    level_options,
    normalize_level,
)
from agent.contradiction_scan import scan_spec_contradictions
from agent.graph import PIPELINE_STEP_COUNT, get_step_label
from agent.pipeline_progress import (
    format_live_progress,
    newly_completed_steps,
    run_pipeline_with_live_progress,
)
from agent.rag_display import resolve_supporting
from agent.regen import (
    can_regenerate_incomplete,
    incomplete_summary,
    prepare_incomplete_regen_state,
)
from agent.state import TestGenState
from services.bootstrap import get_repo
from services.export import test_cases_to_dataframe, to_csv_bytes, to_excel_bytes
from services.ingest import ingest_requirement_document
from services.openai_errors import (
    friendly_openai_error,
    remember_openai_probe_failure,
    resolve_openai_banner_message,
)
from services.project_ui import active_project_name, clean_test_steps
from services.session_project import (
    clear_generate_workflow,
    ensure_generate_workflow_for_project,
)
from services.srs_change import format_srs_change_caption
from services.supabase_auth import require_auth
from theme import (
    apply_theme,
    render_active_project_banner,
    render_back_to_home_link,
    render_generate_field_label,
    render_generate_panel_title,
    render_gradient_metric,
    render_spec_section_header,
)

apply_theme()
require_auth()
render_back_to_home_link()

st.title("🪄 Generate test cases")

try:
    repo = get_repo()
except Exception as e:
    st.error(str(e))
    st.stop()

pid = st.session_state.get("project_id")
if not pid:
    st.warning(
        "Select or create a project on **Home** or **Settings** first. "
        "Your last project is restored automatically after a browser refresh when the URL includes it."
    )
    st.stop()

ensure_generate_workflow_for_project(str(pid))

_projects = repo.list_projects()
render_active_project_banner(active_project_name(_projects, pid))


def _resolve_req_chunks() -> list[dict]:
    """Session chunks first; if missing, reload from Supabase for the prepared document."""
    chunks = st.session_state.get("req_chunks") or []
    if chunks:
        return chunks
    doc = st.session_state.get("req_doc_name")
    if not doc:
        return []
    try:
        fresh = repo.list_requirements_for_document(pid, doc)
        if fresh:
            st.session_state["req_chunks"] = fresh
            return fresh
    except Exception:
        pass
    return []


_req_chunks = _resolve_req_chunks()
chunk_count = len(_req_chunks)
_has_run = bool(st.session_state.get("last_run"))
_upload_nonce = int(st.session_state.get("generate_upload_nonce") or 0)
_level_opts = level_options()
_level_values = [v for _, v in _level_opts]
if st.session_state.get("generate_exhaustiveness") not in _level_values:
    st.session_state["generate_exhaustiveness"] = (
        "standard" if "standard" in _level_values else _level_values[0]
    )

# Settings column is filled first so Prepare can read module_hint / level on click.
col_doc, col_set = st.columns(2, gap="large")

with col_set:
    with st.container(border=True, key="generate_panel_set"):
        render_generate_panel_title("2. Generation settings", kind="set")
        render_generate_field_label("Exhaustiveness")
        exhaustiveness = st.selectbox(
            "Exhaustiveness",
            options=_level_values,
            format_func=lambda v: get_profile(v)["label"],
            help="Controls how many test cases are generated per requirement.",
            key="generate_exhaustiveness",
            label_visibility="collapsed",
        )
        profile = get_profile(exhaustiveness)
        if chunk_count:
            est_cases = estimate_total_cases(exhaustiveness, chunk_count)
            st.markdown(
                f'<div class="gen-field-hint">{html.escape(profile["description"])}</div>'
                f'<span class="gen-estimate-chip">~{est_cases} cases · '
                f"{chunk_count} requirement(s)</span>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="gen-field-hint">{html.escape(profile["description"])}</div>',
                unsafe_allow_html=True,
            )

        render_generate_field_label("Module (optional)")
        module_hint = st.text_input(
            "Module (optional)",
            placeholder="e.g. payments",
            key="generate_module_hint",
            label_visibility="collapsed",
        )
        use_project_history = st.checkbox(
            "Use project history (RAG)",
            value=True,
            help=(
                "Import bugs and test cases on Import first. When enabled, retrieve "
                "similar project history for each requirement. Turn off to generate "
                "from the requirement text only."
            ),
            key="use_project_history",
        )
        generate_clicked = st.button(
            "🚀 Generate test cases",
            disabled=chunk_count < 1,
            type="primary",
            use_container_width=True,
            key="generate_test_cases",
        )

with col_doc:
    with st.container(border=True, key="generate_panel_req"):
        render_generate_panel_title("1. Requirements", kind="req")
        render_generate_field_label("Requirement document")
        st.markdown(
            '<div class="gen-drop-hint">'
            "<strong>Drag &amp; drop</strong> a file into the box below, or click Upload"
            "</div>",
            unsafe_allow_html=True,
        )
        uploaded = st.file_uploader(
            "Requirement document",
            type=["pdf", "docx", "txt", "md"],
            key=f"generate_req_upload_{_upload_nonce}",
            help="PDF, DOCX, TXT, or Markdown. Drag and drop onto the dashed box, or click Upload.",
            label_visibility="collapsed",
        )
        prepare_clicked = st.button(
            "📄 Prepare requirements",
            disabled=uploaded is None,
            type="primary",
            use_container_width=True,
            key="generate_prepare_requirements",
        )

        if chunk_count and not _has_run:
            _prepared_ids = [
                r.get("requirement_id") for r in _req_chunks if r.get("requirement_id")
            ]
            _show_ids = 8
            _id_preview = ", ".join(_prepared_ids[:_show_ids])
            if len(_prepared_ids) > _show_ids:
                _id_preview += f" … and {len(_prepared_ids) - _show_ids} more"
            st.success(
                f"**{chunk_count}** requirement(s) ready — "
                f"{st.session_state.get('req_doc_name', 'document')}"
            )
            st.caption(f"IDs: {_id_preview}")
            _srs_caption = format_srs_change_caption(
                st.session_state.get("srs_change_report") or {}
            )
            if _srs_caption:
                st.caption(_srs_caption)
            if chunk_count <= 10:
                with st.expander(f"Parsed requirement text ({chunk_count})", expanded=False):
                    for row in _req_chunks:
                        rid = row.get("requirement_id") or "—"
                        preview = " ".join((row.get("chunk_text") or "").split())
                        if len(preview) > 160:
                            preview = preview[:160] + "…"
                        st.markdown(f"**{rid}** — {preview}")
        elif chunk_count and _has_run:
            st.markdown(
                '<div class="gen-setup-foot">'
                f"<b>{chunk_count}</b> requirement(s) prepared for "
                f"{html.escape(str(st.session_state.get('req_doc_name', 'document')))}. "
                "See the **Results** / **Run details** tabs below."
                "</div>",
                unsafe_allow_html=True,
            )
        elif st.session_state.get("req_doc_name"):
            st.warning(
                f"No requirements loaded for **{st.session_state['req_doc_name']}**. "
                "Upload the file and click **Prepare requirements** again."
            )
        else:
            st.markdown(
                '<div class="gen-setup-foot">'
                "Upload a document, then prepare before generating."
                "</div>",
                unsafe_allow_html=True,
            )

_clear_l, _clear_r = st.columns([3, 1])
with _clear_r:
    if st.button(
        "Clear workflow",
        type="secondary",
        use_container_width=True,
        key="generate_clear_workflow",
        help="Clears the current upload and generated test cases. Keeps your active project.",
    ):
        clear_generate_workflow()
        st.toast("Workflow cleared — upload a new requirement document.")
        st.rerun()

if prepare_clicked:
    if uploaded is None:
        st.warning("Upload a file first.")
    elif (banner_msg := resolve_openai_banner_message()):
        st.error(banner_msg)
    else:
        try:
            with st.spinner("Parsing requirement IDs, embedding…"):
                data = uploaded.getvalue()
                rows, parse_quality, change_report = ingest_requirement_document(
                    repo, pid, uploaded.name, data, module_hint or None
                )
        except Exception as exc:
            msg = friendly_openai_error(exc)
            if msg:
                remember_openai_probe_failure(exc)
                st.error(msg)
            else:
                raise
        else:
            st.session_state["req_doc_name"] = uploaded.name
            st.session_state["req_chunks"] = rows
            st.session_state["req_parse_quality"] = parse_quality
            st.session_state["srs_change_report"] = change_report
            st.session_state["generate_workflow_project_id"] = str(pid)
            # Clear stale generation UI (old rule IDs); prepared list above stays visible.
            st.session_state.pop("last_run", None)
            detected = [r.get("requirement_id") for r in rows if r.get("requirement_id")]
            st.success(
                f"Stored {len(rows)} requirement(s) for {uploaded.name}: "
                f"{', '.join(detected[:8])}"
                + ("…" if len(detected) > 8 else "")
            )
            caption = format_srs_change_caption(change_report)
            if caption:
                st.info(caption)
            if parse_quality == "ambiguous":
                st.info(
                    "Requirement layout looks ambiguous. When you run **Generate test "
                    "cases**, the Analyst will re-read the document with the LLM "
                    "(~20–45s) to preserve IDs such as FR-2.4."
                )
            elif parse_quality == "synthetic":
                st.caption(
                    "No explicit requirement IDs detected; synthetic REQ-01… labels "
                    "apply unless the Analyst finds IDs in the text."
                )
            st.rerun()

if generate_clicked:
    chunks = _resolve_req_chunks()
    if not chunks:
        st.warning("Complete step 1 (Prepare requirements) first.")
    elif (banner_msg := resolve_openai_banner_message()):
        st.error(banner_msg)
    else:
        if st.session_state.get("retrieval_top_k"):
            os.environ["RETRIEVAL_TOP_K"] = str(st.session_state["retrieval_top_k"])
        if st.session_state.get("retrieval_threshold"):
            os.environ["RETRIEVAL_MATCH_THRESHOLD"] = str(
                st.session_state["retrieval_threshold"]
            )

        # 5.3c: on SRS re-prepare of the same filename, replace generated cases
        # for changed/removed requirement IDs before saving this run.
        change_report = st.session_state.get("srs_change_report") or {}
        replace_ids = list(change_report.get("replace_requirement_ids") or [])
        if replace_ids:
            removed_n = repo.delete_generated_test_cases_for_requirements(
                pid, replace_ids
            )
            id_preview = ", ".join(replace_ids[:8])
            if len(replace_ids) > 8:
                id_preview += "…"
            st.info(
                f"Replacing previously generated cases for changed/removed "
                f"requirements ({id_preview})"
                + (f" — cleared {removed_n} row(s)." if removed_n else ".")
            )

        initial: TestGenState = {
            "project_id": pid,
            "document_name": st.session_state.get("req_doc_name", ""),
            "requirement_chunks": chunks,
            "exhaustiveness_level": normalize_level(exhaustiveness),
            "module_hint": module_hint or None,
            "use_project_history": bool(use_project_history),
            "retrieval_loops": 0,
            "review_round": 0,
            "agent_looped_back": False,
            "pending_queries": [],
            "retrieved_bugs": [],
            "retrieved_tcs": [],
            "generated_cases": [],
            "errors": [],
            "srs_replace_requirement_ids": replace_ids,
        }
        progress = st.progress(0, text="Starting pipeline…")
        pipeline_status = st.status("Generation pipeline", expanded=True)
        live_timer = st.empty()

        # Mutable cell (nonlocal does not work at Streamlit script/module scope).
        _tick_ui = {"logged_step_count": 0}

        def _on_tick(snapshot: dict) -> None:
            fraction, text = format_live_progress(snapshot)
            progress.progress(fraction, text=text)
            running = snapshot.get("running_step")
            if running:
                live_timer.info(text)
            else:
                live_timer.empty()
            for step_index, step_id in newly_completed_steps(
                snapshot, _tick_ui["logged_step_count"]
            ):
                label = get_step_label(step_id)
                pipeline_status.write(f"**Step {step_index} done** — {label}")
            _tick_ui["logged_step_count"] = len(snapshot.get("completed_steps") or [])

        try:
            final = run_pipeline_with_live_progress(
                repo,
                initial,
                on_tick=_on_tick,
            )
            progress.progress(1.0, text="Pipeline complete.")
            live_timer.empty()
            pipeline_status.update(label="Pipeline complete", state="complete")
        except Exception as exc:
            pipeline_status.update(label="Pipeline failed", state="error")
            msg = friendly_openai_error(exc)
            if msg:
                remember_openai_probe_failure(exc)
                st.error(msg)
            else:
                st.error(f"Generation failed: {exc}")
                raise
        else:
            st.session_state["last_run"] = final
            st.session_state["generate_workflow_project_id"] = str(pid)
            # Replace already applied for this prepare; avoid re-deleting next time.
            if replace_ids:
                cleared = dict(change_report)
                cleared["replace_requirement_ids"] = []
                cleared["changed"] = []
                cleared["removed"] = []
                cleared["changed_count"] = 0
                cleared["removed_count"] = 0
                st.session_state["srs_change_report"] = cleared

if st.session_state.get("last_run"):
    fr = st.session_state["last_run"]
    bugs = fr.get("retrieved_bugs") or []
    tcs = fr.get("retrieved_tcs") or []

    _current_chunks = st.session_state.get("req_chunks") or []
    _current_chunk_uuids = {
        str(r.get("id")) for r in _current_chunks if r.get("id")
    }
    _run_chunk_uuids: set[str] = set()
    for _rule in fr.get("atomic_rules") or []:
        for _cid in _rule.get("source_requirement_chunk_ids") or []:
            _run_chunk_uuids.add(str(_cid))
    _stale_run = bool(
        _current_chunk_uuids
        and _run_chunk_uuids
        and (
            not _run_chunk_uuids.issubset(_current_chunk_uuids)
            or _run_chunk_uuids != _current_chunk_uuids
        )
    )
    if _stale_run:
        _chunk_labels = sorted(
            {
                (r.get("requirement_id") or "").strip()
                for r in _current_chunks
                if r.get("requirement_id")
            }
        )
        st.warning(
            "The results below are from a **previous** prepare/generate run (requirement "
            "chunks in the database no longer match this output). "
            f"Current prepared IDs: **{', '.join(_chunk_labels[:10])}**"
            + ("…" if len(_chunk_labels) > 10 else "")
            + ". Click **Generate test cases** again to refresh this section."
        )

    rules = fr.get("atomic_rules") or []
    contradictions = list(fr.get("contradictions") or [])
    if not contradictions and rules:
        contradictions = scan_spec_contradictions(
            rules,
            requirement_chunks=_resolve_req_chunks()
            or list(fr.get("requirement_chunks") or []),
        )

    clarifying_questions = list(fr.get("clarifying_questions") or [])
    if not clarifying_questions and rules:
        from agent.clarifying_questions import build_clarifying_questions

        clarifying_questions = build_clarifying_questions(rules, contradictions)

    rag_stats = fr.get("rag_stats") or {}
    retrieval_summary = fr.get("retrieval_summary") or {}
    report = fr.get("coverage_report") or {}
    dedup_stats = fr.get("batch_dedup_stats") or {}
    constraint_stats = fr.get("constraint_stats") or {}
    expectation_stats = fr.get("expectation_stats") or {}
    spec_fact_stats = fr.get("spec_fact_stats") or {}
    oracle_stats = fr.get("oracle_stats") or {}

    vc = fr.get("validated_cases") or []
    dups = fr.get("duplicates") or []
    invalid_cases = fr.get("invalid_cases") or []
    expectation_rejected = fr.get("expectation_rejected_cases") or []
    spec_fact_rejected = fr.get("spec_fact_rejected_cases") or []
    quality_review_rejected = fr.get("oracle_rejected_cases") or []
    n_spec = len(contradictions) + len(clarifying_questions)
    n_rejected = (
        len(dups)
        + len(invalid_cases)
        + len(expectation_rejected)
        + len(spec_fact_rejected)
        + len(quality_review_rejected)
    )

    cmap = {str(c.get("id")): c for c in st.session_state.get("req_chunks") or []}
    rule_by_id = {r.get("rule_id"): r for r in rules}

    def show_traceability(case: dict) -> None:
        lr = case.get("linked_requirement")
        rule = rule_by_id.get(lr) if lr else None
        if lr:
            scope = (rule.get("screen") if rule else None) or "General"
            st.markdown(
                f"- **Requirement:** `{lr}` *(scope: {scope})*"
            )
        ids = case.get("source_requirement_chunk_ids") or []
        for uid in ids:
            ch = cmap.get(str(uid))
            if ch:
                st.markdown(
                    f"- **Requirement chunk** `{uid}` (index {ch.get('chunk_index')}): "
                    f"{(ch.get('chunk_text') or '')[:300]}…"
                )
        links = resolve_supporting(case, bugs, tcs)
        if links:
            st.markdown("**Linked project history**")
            for link in links:
                kind = "Bug" if link["kind"] == "bug" else "Test case"
                src = link.get("link_source") or "llm"
                src_label = "LLM citation" if src == "llm" else "semantic fallback"
                sim = link.get("similarity")
                sim_t = f", retrieval sim={float(sim):.2f}" if sim is not None else ""
                retrieved_for_rule = ""
                if rule and lr:
                    rule_bugs = set(rule.get("retrieved_bug_ids") or [])
                    rule_tcs = set(rule.get("retrieved_tc_ids") or [])
                    if link["id"] in rule_bugs or link["id"] in rule_tcs:
                        retrieved_for_rule = f" · retrieved for {lr}"
                st.markdown(
                    f"- **{kind}** `{link['id']}` — {link.get('title')} "
                    f"(*{src_label}*{sim_t}{retrieved_for_rule})"
                )
        elif bugs or tcs:
            st.markdown("- *No history link on this case.*")

    def _render_case_card(case: dict, links: list) -> None:
        test_type = (case.get("test_type") or "").strip().lower()
        chip_class = {
            "positive": "tc-positive",
            "negative": "tc-negative",
            "edge": "tc-edge",
            "boundary": "tc-boundary",
        }.get(test_type, "tc-default")
        chip_label = html.escape((case.get("test_type") or "test").upper())
        tc_id = html.escape(str(case.get("testcase_id") or "TC pending"))
        title = html.escape(str(case.get("title") or ""))
        history_html = (
            '<span class="tc-history">✨ history linked</span>' if links else ""
        )

        st.markdown(
            f'<div class="tc-header">'
            f'<span class="tc-id">{tc_id}</span>'
            f'<span class="tc-chip {chip_class}">{chip_label}</span>'
            f'<span class="tc-title">{title}</span>'
            f"{history_html}"
            f"</div>",
            unsafe_allow_html=True,
        )

        if case.get("preconditions"):
            st.markdown(
                '<div class="tc-section-label tc-precond">📌 Preconditions</div>',
                unsafe_allow_html=True,
            )
            st.markdown(case["preconditions"])

        st.markdown(
            '<div class="tc-section-label tc-steps">📝 Test steps</div>',
            unsafe_allow_html=True,
        )
        for idx, step in enumerate(clean_test_steps(case.get("steps")), start=1):
            st.markdown(f"{idx}. {step}")

        if case.get("expected_result"):
            st.markdown(
                '<div class="tc-section-label tc-expect">🎯 Expected result</div>',
                unsafe_allow_html=True,
            )
            st.markdown(case["expected_result"])

    def _render_duplicate_entry(case: dict, index: int) -> None:
        title = case.get("title") or "Untitled"
        reason = str(case.get("duplicate_reason") or "")

        with st.expander(f"🚫 {title[:100]}", expanded=False):
            if reason == "batch_title_duplicate":
                st.markdown(
                    "**Why:** Same title as another generated case in **this run** "
                    "(only the first is accepted)."
                )
                st.markdown(
                    f"**Matched case in this run:** **{case.get('similar_to_title') or '—'}**"
                )
            elif reason == "cross_requirement_scenario_duplicate":
                st.markdown(
                    "**Why:** Same failure scenario as another requirement in this run "
                    "(shared error code or identical failure expected result). "
                    "Only the first occurrence is kept."
                )
                other_req = case.get("similar_to_requirement") or "—"
                st.markdown(
                    f"**Matched case:** **{case.get('similar_to_title') or '—'}** "
                    f"(requirement **{other_req}**)"
                )
                if case.get("scenario_match"):
                    st.caption(f"Match: {case.get('scenario_match')}")
            elif reason.startswith("library_similarity"):
                sim_raw = reason.split("=", 1)[-1] if "=" in reason else ""
                try:
                    sim_label = f"{float(sim_raw):.0%}"
                except ValueError:
                    sim_label = sim_raw or "—"
                lib_title = case.get("similar_to_title") or "—"
                lib_type = (case.get("similar_to_test_type") or "").strip()
                lib_id = (case.get("similar_to_id") or "").strip()
                st.markdown(
                    "**Why:** Too similar to a test case already in your project library "
                    "(imported history or a prior generation run)."
                )
                st.markdown(f"**Matched library test case:** **{lib_title}**")
                if lib_type:
                    st.caption(f"Type: {lib_type.title()}")
                if sim_label:
                    st.caption(f"Similarity: **{sim_label}**")
                if lib_id:
                    st.caption(
                        f"Library row id: `{lib_id}` — open **Library** to view the full "
                        f"historical test case."
                    )
            else:
                st.markdown(f"**Reason:** {reason}")
            if reason == "batch_semantic_duplicate":
                st.markdown(
                    "**Why:** Semantic duplicate within the same requirement and test type "
                    "(kept case is shown below)."
                )
                st.markdown(
                    f"**Matched case in this run:** **{case.get('similar_to_title') or '—'}**"
                )
                sim = case.get("similarity")
                if sim is not None:
                    try:
                        st.caption(f"Similarity: **{float(sim):.0%}**")
                    except (TypeError, ValueError):
                        st.caption(f"Similarity: **{sim}**")

            st.divider()
            st.markdown("**Generated duplicate (not accepted):**")
            _render_case_card(case, [])

    tab_results, tab_spec, tab_rejected, tab_details = st.tabs(
        [
            f"Results ({len(vc)})",
            f"Spec issues ({n_spec})",
            f"Rejected ({n_rejected})",
            "Run details",
        ]
    )

    with tab_results:
        if report:
            st.markdown("### Coverage")
            c1, c2, c3, c4 = st.columns(4)
            total_rules = report.get("rule_count", 0)
            with c1:
                render_gradient_metric(
                    "Fully covered",
                    f"{report.get('rules_fully_covered', 0)}/{total_rules}",
                    "teal",
                    help=(
                        "Requirements with every planned test type filled for this "
                        "exhaustiveness level. Blocked contradictory requirements count "
                        "in the total but not as covered."
                    ),
                )
            with c2:
                render_gradient_metric(
                    "Partially covered",
                    report.get("rules_partially_covered", 0),
                    "warm",
                    help=(
                        "Requirements with at least one accepted test case, but still "
                        "missing one or more planned types (for example 2/3 negatives)."
                    ),
                )
            with c3:
                render_gradient_metric(
                    "Total test cases",
                    report.get("total_cases", 0),
                    "purple",
                )
            with c4:
                dup_help = "Duplicates removed before save."
                if dedup_stats:
                    dup_help = (
                        f"Title: {dedup_stats.get('removed_title', 0)} · "
                        f"Verbatim: {dedup_stats.get('removed_verbatim', 0)} · "
                        f"Cross-req: {dedup_stats.get('removed_cross_req', 0)} · "
                        f"Semantic batch: {dedup_stats.get('removed_semantic', 0)} · "
                        f"Library: {dedup_stats.get('removed_library', 0)}"
                    )
                render_gradient_metric(
                    "Duplicates found",
                    len(dups),
                    "indigo",
                    help=dup_help,
                )
            caption_bits: list[str] = []
            not_covered = int(report.get("rules_not_covered") or 0)
            blocked = int(report.get("blocked_rule_count") or 0)
            if not_covered:
                caption_bits.append(
                    f"**{not_covered}** not covered (generatable, but 0 accepted cases)"
                )
            if blocked:
                caption_bits.append(
                    f"**{blocked}** blocked as `requires_clarification`"
                )
            if caption_bits:
                st.caption(" · ".join(caption_bits))
            if report.get("per_rule"):
                with st.expander("Coverage by requirement", expanded=False):
                    for row in report["per_rule"]:
                        if row.get("status") == "requires_clarification":
                            st.markdown(
                                f"🚫 **{row.get('rule_id')}** — blocked pending clarification"
                            )
                            continue
                        req = row.get("required", {})
                        cnt = row.get("counts", {})
                        cells = " · ".join(
                            f"{t}: {cnt.get(t, 0)}/{req.get(t, 0)}" for t in req
                        )
                        status = row.get("coverage_status") or (
                            "fully_covered"
                            if row.get("satisfied")
                            else "partially_covered"
                        )
                        if status == "fully_covered":
                            icon = "✅"
                            label = "fully covered"
                        elif status == "partially_covered":
                            icon = "⚠️"
                            label = "partially covered"
                        else:
                            icon = "❌"
                            label = "not covered"
                        st.markdown(
                            f"{icon} **{row.get('rule_id')}** — {cells} *({label})*"
                        )

            _regen_ok = (
                not _stale_run
                and can_regenerate_incomplete(fr)
                and chunk_count >= 1
            )
            if _regen_ok:
                _regen_info = incomplete_summary(fr)
                _n_rules = int(_regen_info.get("rule_count") or 0)
                if _n_rules > 0:
                    _partial = int(_regen_info.get("partially_covered") or 0)
                    _missing = int(_regen_info.get("not_covered") or 0)
                    _bits: list[str] = []
                    if _partial:
                        _bits.append(f"{_partial} partially covered")
                    if _missing:
                        _bits.append(f"{_missing} not covered")
                    _status = " · ".join(_bits) if _bits else "incomplete"
                    with st.expander(
                        f"Fill gaps — {_n_rules} requirement(s) still need testcases",
                        expanded=False,
                    ):
                        st.markdown(
                            f"**{_n_rules}** requirement(s) still need more test cases "
                            f"({_status}). "
                            "Usually this means drafts were generated but **not kept** — "
                            "for example they conflicted with another requirement, "
                            "failed a quality check, or were missing concrete data "
                            "(see the **Rejected** tab for those drafts). "
                            "Click **Regenerate incomplete** to try again for only the "
                            "**missing** types. Requirements that are already fully "
                            "covered are left alone."
                        )
                        if st.button(
                            f"🔄 Regenerate incomplete requirement ({_n_rules})",
                            type="primary",
                            use_container_width=True,
                            key="regenerate_incomplete_requirements",
                            help=(
                                "Re-run generation only for partially covered and "
                                "not-covered requirements. Uses prior rejection feedback "
                                "when available."
                            ),
                        ):
                            if (banner_msg := resolve_openai_banner_message()):
                                st.error(banner_msg)
                            else:
                                regen_initial = prepare_incomplete_regen_state(fr)
                                if not regen_initial.get("requirement_chunks"):
                                    regen_initial["requirement_chunks"] = (
                                        _resolve_req_chunks()
                                    )
                                progress = st.progress(
                                    0, text="Starting incomplete regen…"
                                )
                                pipeline_status = st.status(
                                    "Incomplete-requirement regeneration",
                                    expanded=True,
                                )
                                live_timer = st.empty()
                                _tick_ui = {"logged_step_count": 0}

                                def _on_regen_tick(snapshot: dict) -> None:
                                    fraction, text = format_live_progress(snapshot)
                                    progress.progress(fraction, text=text)
                                    running = snapshot.get("running_step")
                                    if running:
                                        live_timer.info(text)
                                    else:
                                        live_timer.empty()
                                    for step_index, step_id in newly_completed_steps(
                                        snapshot, _tick_ui["logged_step_count"]
                                    ):
                                        label = get_step_label(step_id)
                                        pipeline_status.write(
                                            f"**Step {step_index} done** — {label}"
                                        )
                                    _tick_ui["logged_step_count"] = len(
                                        snapshot.get("completed_steps") or []
                                    )

                                try:
                                    final = run_pipeline_with_live_progress(
                                        repo,
                                        regen_initial,
                                        on_tick=_on_regen_tick,
                                        regen=True,
                                    )
                                    progress.progress(1.0, text="Regen complete.")
                                    live_timer.empty()
                                    pipeline_status.update(
                                        label="Incomplete regen complete",
                                        state="complete",
                                    )
                                except Exception as exc:
                                    pipeline_status.update(
                                        label="Incomplete regen failed",
                                        state="error",
                                    )
                                    msg = friendly_openai_error(exc)
                                    if msg:
                                        remember_openai_probe_failure(exc)
                                        st.error(msg)
                                    else:
                                        st.error(f"Regeneration failed: {exc}")
                                        raise
                                else:
                                    accepted_rids = {
                                        str(c.get("linked_requirement") or "")
                                        for c in (final.get("validated_cases") or [])
                                        if c.get("linked_requirement")
                                        and not c.get("_already_persisted")
                                    }

                                    def _merge_rejection_list(
                                        new_list: list,
                                        old_list: list,
                                        violation_key: str,
                                    ) -> list:
                                        kept_old = [
                                            c
                                            for c in old_list
                                            if str(c.get("linked_requirement") or "")
                                            not in accepted_rids
                                        ]
                                        seen_titles = {
                                            c.get("title") for c in new_list
                                        }
                                        for c in kept_old:
                                            if c.get("title") not in seen_titles:
                                                new_list = list(new_list) + [c]
                                        return new_list

                                    final = dict(final)

                                    old_invalid = fr.get("invalid_cases") or []
                                    if old_invalid:
                                        final["invalid_cases"] = _merge_rejection_list(
                                            final.get("invalid_cases") or [],
                                            old_invalid,
                                            "constraint_violations",
                                        )

                                    old_spec_fact = (
                                        fr.get("spec_fact_rejected_cases") or []
                                    )
                                    if old_spec_fact:
                                        final["spec_fact_rejected_cases"] = (
                                            _merge_rejection_list(
                                                final.get("spec_fact_rejected_cases")
                                                or [],
                                                old_spec_fact,
                                                "spec_fact_violations",
                                            )
                                        )

                                    st.session_state["last_run"] = final
                                    st.session_state[
                                        "generate_workflow_project_id"
                                    ] = str(pid)
                                    st.rerun()

        st.markdown(f"### Test cases by requirement ({len(vc)} total)")

        if vc:
            st.info(
                "Each row below is one **requirement**. "
                "**Click a row to expand** and view the generated test cases "
                "(steps, expected results, and traceability)."
            )
            st.caption(
                "Download accepted cases from **this run only**. "
                "For all project test cases (all runs and imports), use **Library**."
            )
            df_run = test_cases_to_dataframe(vc)
            dl1, dl2 = st.columns(2)
            with dl1:
                st.download_button(
                    "⬇️ Download CSV (this run)",
                    data=to_csv_bytes(df_run),
                    file_name="generated_test_cases.csv",
                    mime="text/csv",
                    type="primary",
                    use_container_width=True,
                    key="generate_dl_csv",
                )
            with dl2:
                st.download_button(
                    "⬇️ Download Excel (this run)",
                    data=to_excel_bytes(df_run),
                    file_name="generated_test_cases.xlsx",
                    mime=(
                        "application/vnd.openxmlformats-officedocument"
                        ".spreadsheetml.sheet"
                    ),
                    type="primary",
                    use_container_width=True,
                    key="generate_dl_xlsx",
                )

            grouped_cases: dict[str, list[dict]] = {}
            for case in vc:
                grouped_cases.setdefault(
                    case.get("linked_requirement") or "Unmapped", []
                ).append(case)

            for req_id, req_cases in grouped_cases.items():
                req = rule_by_id.get(req_id) or {}
                req_summary = req.get("summary") or "Requirement not found in current run"
                scope = req.get("screen") or "General"
                module = req.get("module") or "—"
                with st.expander(
                    f"{req_id} — {req_summary[:120]} ({len(req_cases)} test case(s))",
                    expanded=False,
                ):
                    st.caption(f"scope: {scope} · module: {module}")
                    for case in req_cases:
                        links = resolve_supporting(case, bugs, tcs)
                        _render_case_card(case, links)
                        with st.expander("Traceability and raw details", expanded=False):
                            show_traceability(case)
                            st.json({k: v for k, v in case.items() if k != "steps"})
                        st.divider()
        else:
            st.caption("No accepted test cases in this run.")

    with tab_spec:
        if n_spec == 0:
            st.caption(
                "No specification contradictions or open questions for this run."
            )
        else:
            if contradictions:
                render_spec_section_header(
                    "Specification contradictions",
                    kind="conflict",
                    count=len(contradictions),
                    blurb=(
                        "These requirements were not generated until the conflict "
                        "is resolved."
                    ),
                )
                for row in contradictions:
                    related = row.get("related_rule_ids") or []
                    rel_text = (
                        f" (related: {', '.join(related)})" if related else ""
                    )
                    st.markdown(
                        f"- **{row.get('rule_id')}**{rel_text}: {row.get('issue')}"
                    )

            if clarifying_questions:
                render_spec_section_header(
                    "Open questions for spec author",
                    kind="questions",
                    count=len(clarifying_questions),
                    blurb=(
                        "Advisory questions about underspecified or conflicting "
                        "behavior. These do not block testcase generation — they are "
                        "prompts for you to tighten the SRS."
                    ),
                )
                for i, q in enumerate(clarifying_questions):
                    ids = q.get("rule_ids") or []
                    id_label = ", ".join(str(r) for r in ids) if ids else "—"
                    with st.expander(
                        f"Q{i + 1}. [{id_label}] {(q.get('question') or '')[:100]}",
                        expanded=False,
                    ):
                        st.markdown(f"**Question:** {q.get('question') or '—'}")
                        if q.get("why_it_matters"):
                            st.markdown(
                                f"**Why it matters:** {q.get('why_it_matters')}"
                            )
                        src = (q.get("source") or "").strip()
                        if src:
                            st.caption(f"Source: {src}")

    with tab_rejected:
        if n_rejected == 0:
            st.caption("No rejected cases for this run.")
        else:
            if constraint_stats:
                rejected = int(constraint_stats.get("invalid_cases") or 0)
                valid = int(constraint_stats.get("valid_cases") or 0)
                if rejected:
                    st.warning(
                        f"Constraint validation rejected **{rejected}** generated "
                        f"case(s) before dedup/save. **{valid}** case(s) passed "
                        "constraint checks."
                    )

            if expectation_stats:
                rejected = int(expectation_stats.get("rejected_cases") or 0)
                valid = int(expectation_stats.get("valid_cases") or 0)
                if rejected:
                    st.warning(
                        f"Expectation validation rejected **{rejected}** "
                        "negative/boundary case(s) that claimed rejection for a "
                        f"constraint-valid value. **{valid}** case(s) passed "
                        "expectation checks."
                    )

            if spec_fact_stats:
                rejected = int(spec_fact_stats.get("rejected_cases") or 0)
                valid = int(spec_fact_stats.get("valid_cases") or 0)
                if rejected:
                    st.warning(
                        f"Spec-fact validation rejected **{rejected}** case(s) with "
                        "quiet-hour times or DST day lengths that do not match the "
                        f"specification. **{valid}** case(s) passed."
                    )

            if oracle_stats:
                rejected = int(oracle_stats.get("rejected_cases") or 0)
                valid = int(oracle_stats.get("valid_cases") or 0)
                if rejected:
                    st.warning(
                        f"Quality review flagged **{rejected}** generated case(s) as "
                        f"vague or unexecutable. **{valid}** case(s) look ready for "
                        "manual testing."
                    )

            if dups:
                st.markdown(f"### Marked duplicates ({len(dups)})")
                st.caption(
                    "These were generated but not accepted. Expand a row to see which "
                    "library or in-run case it matched."
                )
                for i, c in enumerate(dups):
                    _render_duplicate_entry(c, i)

            if invalid_cases:
                st.markdown(
                    f"### Constraint-rejected cases ({len(invalid_cases)})"
                )
                st.caption(
                    "These cases were generated but rejected before save because they "
                    "appear to violate a parsed requirement constraint."
                )
                for case in invalid_cases:
                    title = case.get("title") or "Untitled"
                    with st.expander(f"🚫 {title[:100]}", expanded=False):
                        for issue in case.get("constraint_violations") or []:
                            st.markdown(f"- {issue}")
                        st.divider()
                        _render_case_card(case, [])

            if expectation_rejected:
                st.markdown(
                    f"### Invalid negative expectations ({len(expectation_rejected)})"
                )
                st.caption(
                    "These negative or boundary cases were rejected because they expect "
                    "failure for a value that satisfies parsed limits — the test logic "
                    "is wrong, not the spec."
                )
                for case in expectation_rejected:
                    title = case.get("title") or "Untitled"
                    with st.expander(f"🚫 {title[:100]}", expanded=False):
                        for issue in case.get("expectation_violations") or []:
                            st.markdown(f"- {issue}")
                        st.divider()
                        _render_case_card(case, [])

            if spec_fact_rejected:
                st.markdown(
                    f"### Spec-fact rejected cases ({len(spec_fact_rejected)})"
                )
                st.caption(
                    "These cases assert quiet-hour times or DST day lengths that conflict "
                    "with (or are absent from) the parsed specification facts."
                )
                for case in spec_fact_rejected:
                    title = case.get("title") or "Untitled"
                    with st.expander(f"🚫 {title[:100]}", expanded=False):
                        for issue in case.get("spec_fact_violations") or []:
                            st.markdown(f"- {issue}")
                        st.divider()
                        _render_case_card(case, [])

            if quality_review_rejected:
                st.markdown(
                    f"### Cases needing revision ({len(quality_review_rejected)})"
                )
                st.caption(
                    "These drafts were not kept because they are too vague, "
                    "contradictory, or missing concrete data a manual tester would need."
                )
                for case in quality_review_rejected:
                    title = case.get("title") or "Untitled"
                    with st.expander(f"🚫 {title[:100]}", expanded=False):
                        for issue in case.get("oracle_findings") or []:
                            st.markdown(f"- {issue}")
                        st.divider()
                        _render_case_card(case, [])

    with tab_details:
        if rag_stats or retrieval_summary:
            st.markdown("### Project history (RAG)")
            if rag_stats.get("use_project_history") is False:
                reason = rag_stats.get("skip_reason") or retrieval_summary.get(
                    "skip_reason"
                )
                if reason == "use_project_history_disabled":
                    st.caption("Project history was turned off for this run.")
                else:
                    st.caption("No project history was used for this run.")
            else:
                # Prefer retrieve-step counters; fall back to retrieval_summary
                # (older runs where enrich_rag overwrote rag_stats keys).
                retrieved_n = int(rag_stats.get("retrieved_bugs") or 0) + int(
                    rag_stats.get("retrieved_tcs") or 0
                )
                used_n = int(rag_stats.get("used_bugs") or 0) + int(
                    rag_stats.get("used_tcs") or 0
                )
                dropped_n = int(rag_stats.get("dropped_bugs") or 0) + int(
                    rag_stats.get("dropped_tcs") or 0
                )
                if retrieved_n == 0 and used_n == 0 and dropped_n == 0:
                    retrieved_n = int(
                        retrieval_summary.get("retrieved_bug_count") or 0
                    ) + int(retrieval_summary.get("retrieved_tc_count") or 0)
                    used_n = int(retrieval_summary.get("used_bug_count") or 0) + int(
                        retrieval_summary.get("used_tc_count") or 0
                    )
                    dropped_n = int(
                        retrieval_summary.get("dropped_bug_count") or 0
                    ) + int(retrieval_summary.get("dropped_tc_count") or 0)
                    if retrieved_n == 0 and used_n == 0:
                        retrieved_n = int(
                            rag_stats.get("retrieved_bug_count") or 0
                        ) + int(rag_stats.get("retrieved_tc_count") or 0)
                        used_n = retrieved_n
                c_rag1, c_rag2, c_rag3 = st.columns(3)
                with c_rag1:
                    render_gradient_metric("Retrieved", retrieved_n, "purple")
                with c_rag2:
                    render_gradient_metric(
                        "Used in prompts",
                        used_n,
                        "teal",
                        help=(
                            "History items similar enough to this SRS to include "
                            "when writing test cases."
                        ),
                    )
                with c_rag3:
                    render_gradient_metric(
                        "Dropped as off-topic",
                        dropped_n,
                        "warm",
                        help=(
                            "Imported history from a different product area — "
                            "excluded so it does not confuse generation."
                        ),
                    )
                if dropped_n:
                    st.caption(
                        "Off-topic imports (different product domain) were excluded "
                        "so they do not pollute generated cases."
                    )

        if rules:
            blocked = sum(
                1 for r in rules if r.get("status") == "requires_clarification"
            )
            generatable = len(rules) - blocked
            st.markdown(f"### Analyzed requirements ({len(rules)})")
            st.caption(
                "The requirement rules this run worked from (IDs, scope, blocked status) "
                "— not the accepted test cases (those are on **Results**)."
            )
            if blocked:
                st.caption(
                    f"{generatable} generatable · {blocked} blocked pending clarification"
                )
            scopes_seen = sorted({(r.get("screen") or "General") for r in rules})
            st.caption(
                "Scopes used for history lookup: " + ", ".join(scopes_seen)
            )
            with st.container(key="gen_details_req_list"):
                with st.expander(
                    "Requirement list (IDs, scope, summary)",
                    expanded=False,
                ):
                    for r in rules:
                        scope = r.get("screen") or "General"
                        module = r.get("module") or ""
                        status = r.get("status") or "active"
                        tags = f"*(scope: {scope}"
                        if module:
                            tags += f", module: {module}"
                        if status == "requires_clarification":
                            tags += ", **blocked**"
                        tags += ")*"
                        st.markdown(
                            f"- **{r.get('rule_id')}** {tags}: {r.get('summary')}"
                        )

        if constraint_stats:
            rejected = int(constraint_stats.get("invalid_cases") or 0)
            valid = int(constraint_stats.get("valid_cases") or 0)
            if not rejected:
                st.caption(
                    f"Constraint validation passed for all **{valid}** generated case(s)."
                )

        if expectation_stats:
            rejected = int(expectation_stats.get("rejected_cases") or 0)
            valid = int(expectation_stats.get("valid_cases") or 0)
            if not rejected and int(expectation_stats.get("input_cases") or 0) > 0:
                st.caption(
                    f"Expectation validation passed for all **{valid}** checked case(s)."
                )

        if spec_fact_stats:
            rejected = int(spec_fact_stats.get("rejected_cases") or 0)
            valid = int(spec_fact_stats.get("valid_cases") or 0)
            if not rejected and int(spec_fact_stats.get("input_cases") or 0) > 0:
                st.caption(
                    f"Spec-fact validation passed for all **{valid}** checked case(s)."
                )

        if oracle_stats:
            rejected = int(oracle_stats.get("rejected_cases") or 0)
            valid = int(oracle_stats.get("valid_cases") or 0)
            if not rejected:
                st.caption(
                    f"Quality review passed for all **{valid}** generated case(s)."
                )

        if fr.get("reasoning"):
            with st.container(key="gen_details_reasoning"):
                with st.expander("Agent reasoning", expanded=False):
                    st.write(fr.get("reasoning"))

        if fr.get("agent_looped_back"):
            st.write(
                "**Coverage reviewer triggered regeneration** to fill gaps."
            )

    if fr.get("errors"):
        st.error(fr.get("errors"))
