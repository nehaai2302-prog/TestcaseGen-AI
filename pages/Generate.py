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
from agent.graph import PIPELINE_STEP_COUNT, get_step_label
from agent.pipeline_progress import (
    format_live_progress,
    newly_completed_steps,
    run_pipeline_with_live_progress,
)
from agent.rag_display import resolve_supporting
from agent.state import TestGenState
from services.bootstrap import get_repo
from services.export import test_cases_to_dataframe, to_csv_bytes, to_excel_bytes
from services.ingest import ingest_requirement_document
from theme import apply_theme, render_back_to_home_link

apply_theme()
render_back_to_home_link()

st.title("🪄 Generate test cases")

try:
    repo = get_repo()
except Exception as e:
    st.error(str(e))
    st.stop()

pid = st.session_state.get("project_id")
if not pid:
    st.warning("Select or create a project from the home page or Settings first.")
    st.stop()

st.markdown(
    "Import **bug reports** and **test cases** on the Import page first so generation can "
    "retrieve similar project history (RAG) and link new tests to that history."
)

uploaded = st.file_uploader("Requirement document", type=["pdf", "docx", "txt", "md"])

_level_opts = level_options()
_level_values = [v for _, v in _level_opts]
default_idx = _level_values.index("standard") if "standard" in _level_values else 0
exhaustiveness = st.selectbox(
    "Exhaustiveness level",
    options=_level_values,
    format_func=lambda v: get_profile(v)["label"],
    index=default_idx,
    help="Controls how many test cases are generated per requirement.",
)
profile = get_profile(exhaustiveness)
st.caption(profile["description"])

module_hint = st.text_input("Optional module hint", placeholder="e.g. payments")

chunk_count = len(st.session_state.get("req_chunks") or [])
if chunk_count:
    est_requirements = chunk_count
    est_cases = estimate_total_cases(exhaustiveness, est_requirements)
    st.info(
        f"Step 1 complete — **{chunk_count}** requirement(s) ready. "
        f"Estimated **~{est_cases}** test cases at this level. "
        f"You can run **Step 2** below."
    )

st.markdown(
    "**Step 1:** Ingest requirements from your document  \n"
    "**Step 2:** Generate test cases *(available after step 1)*"
)
col_a, col_b = st.columns(2)
with col_a:
    if st.button(
        "📄 Prepare requirements",
        disabled=uploaded is None,
        type="primary",
        use_container_width=True,
        key="generate_prepare_requirements",
    ):
        if uploaded is None:
            st.warning("Upload a file first.")
        else:
            with st.spinner("Parsing requirement IDs, embedding…"):
                data = uploaded.getvalue()
                rows = ingest_requirement_document(
                    repo, pid, uploaded.name, data, module_hint or None
                )
                st.session_state["req_doc_name"] = uploaded.name
                st.session_state["req_chunks"] = rows
                detected = [r.get("requirement_id") for r in rows if r.get("requirement_id")]
                st.success(
                    f"Stored {len(rows)} requirement(s) for {uploaded.name}: "
                    f"{', '.join(detected[:8])}"
                    + ("…" if len(detected) > 8 else "")
                )
                st.rerun()

with col_b:
    if st.button(
        "🚀 Generate test cases",
        disabled=not st.session_state.get("req_chunks"),
        type="primary",
        use_container_width=True,
        key="generate_test_cases",
    ):
        chunks = st.session_state.get("req_chunks") or []
        if not chunks:
            st.warning("Complete step 1 (Prepare requirements) first.")
        else:
            if st.session_state.get("retrieval_top_k"):
                os.environ["RETRIEVAL_TOP_K"] = str(st.session_state["retrieval_top_k"])
            if st.session_state.get("retrieval_threshold"):
                os.environ["RETRIEVAL_MATCH_THRESHOLD"] = str(
                    st.session_state["retrieval_threshold"]
                )
            initial: TestGenState = {
                "project_id": pid,
                "document_name": st.session_state.get("req_doc_name", ""),
                "requirement_chunks": chunks,
                "exhaustiveness_level": normalize_level(exhaustiveness),
                "module_hint": module_hint or None,
                "retrieval_loops": 0,
                "review_round": 0,
                "agent_looped_back": False,
                "pending_queries": [],
                "retrieved_bugs": [],
                "retrieved_tcs": [],
                "generated_cases": [],
                "errors": [],
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
                    pipeline_status.write(
                        f"**Step {step_index} done** — {label}"
                    )
                _tick_ui["logged_step_count"] = len(
                    snapshot.get("completed_steps") or []
                )

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
                st.error(f"Generation failed: {exc}")
                raise
            else:
                st.session_state["last_run"] = final

if st.session_state.get("last_run"):
    fr = st.session_state["last_run"]
    bugs = fr.get("retrieved_bugs") or []
    tcs = fr.get("retrieved_tcs") or []

    rules = fr.get("atomic_rules") or []
    if rules:
        st.markdown(f"### Requirements ({len(rules)})")
        scopes_seen = sorted({(r.get("screen") or "General") for r in rules})
        st.caption(
            "Scopes identified for RAG (UI screen, service, or functional area): "
            + ", ".join(scopes_seen)
        )
        with st.expander("Detected requirements", expanded=False):
            for r in rules:
                scope = r.get("screen") or "General"
                module = r.get("module") or ""
                tags = f"*(scope: {scope}"
                if module:
                    tags += f", module: {module}"
                tags += ")*"
                st.markdown(f"- **{r.get('rule_id')}** {tags}: {r.get('summary')}")

    report = fr.get("coverage_report") or {}
    if report:
        st.markdown("### Coverage")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Requirements covered", f"{report.get('rules_fully_covered', 0)}/{report.get('rule_count', 0)}")
        c2.metric("Total cases", report.get("total_cases", 0))
        c3.metric(
            "Duplicates found",
            len(fr.get("duplicates") or []),
            help="Same title in this run, or ≥88% similar to an existing library case.",
        )
        c4.metric("Gaps remaining", report.get("gap_count", 0))
        if report.get("per_rule"):
            with st.expander("Per-requirement coverage matrix", expanded=False):
                for row in report["per_rule"]:
                    req = row.get("required", {})
                    cnt = row.get("counts", {})
                    cells = " · ".join(f"{t}: {cnt.get(t, 0)}/{req.get(t, 0)}" for t in req)
                    icon = "✅" if row.get("satisfied") else "⚠️"
                    st.markdown(f"{icon} **{row.get('rule_id')}** — {cells}")

    if fr.get("reasoning"):
        with st.expander("Agent reasoning", expanded=False):
            st.write(fr.get("reasoning"))

    if fr.get("agent_looped_back"):
        st.write("**Coverage reviewer triggered regeneration** to fill gaps.")

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
                # Note if linked item came from this rule's screen-aware pool
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
        for idx, step in enumerate(case.get("steps") or [], start=1):
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

            st.divider()
            st.markdown("**Generated duplicate (not accepted):**")
            _render_case_card(case, [])

    vc = fr.get("validated_cases") or []
    st.markdown(f"### Accepted test cases ({len(vc)})")

    if vc:
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
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True,
                key="generate_dl_xlsx",
            )

    grouped_cases: dict[str, list[dict]] = {}
    for case in vc:
        grouped_cases.setdefault(case.get("linked_requirement") or "Unmapped", []).append(case)

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

    dups = fr.get("duplicates") or []
    if dups:
        st.markdown(f"### Marked duplicates ({len(dups)})")
        st.caption(
            "These were generated but not accepted. Expand a row to see which library "
            "or in-run case it matched."
        )
        for i, c in enumerate(dups):
            _render_duplicate_entry(c, i)

    if fr.get("errors"):
        st.error(fr.get("errors"))
