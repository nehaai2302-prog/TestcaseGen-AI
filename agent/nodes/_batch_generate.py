"""Shared batch LLM generation for happy-path and destructive agents."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agent.exhaustiveness import get_profile
from agent.formatting import bug_lines, tc_lines
from agent.llm import get_chat_model
from agent.models import TestCaseGen, TestCasesBatch
from agent.prompts import (
    COMBINED_SYSTEM,
    COMBINED_USER,
    CONTEXT_BLOCK,
    DESTRUCTIVE_SYSTEM,
    DESTRUCTIVE_USER,
    HAPPY_PATH_SYSTEM,
    HAPPY_PATH_USER,
    RAG_INSTRUCTION_EMPTY,
    RAG_INSTRUCTION_REQUIRED,
)
from services.constraint_index import (
    build_project_constraint_index,
    constraints_for_rule,
    format_constraints_for_prompt,
)


def _batch_spec_lines(
    rules: list[dict[str, Any]],
    quotas: dict[str, int],
) -> str:
    lines: list[str] = []
    for r in rules:
        rid = r.get("rule_id", "")
        parts = [f"{t}: {quotas[t]}" for t in quotas if quotas.get(t, 0) > 0]
        lines.append(f"- {rid} ({r.get('summary', '')}): {', '.join(parts)}")
    return "\n".join(lines)


def _cases_to_dicts(cases: list[TestCaseGen]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for tc in cases:
        d = tc.model_dump()
        d["source"] = "generated"
        d["is_duplicate"] = False
        if d.get("supporting_bug_ids") or d.get("supporting_test_case_ids"):
            d["rag_link_source"] = "llm"
        out.append(d)
    return out


def _normalize_generated_case(
    case: dict[str, Any],
    requirement: dict[str, Any],
) -> dict[str, Any]:
    """Force one generated case to map to its source requirement."""
    req_id = requirement.get("rule_id") or requirement.get("requirement_id") or ""
    chunk_ids = requirement.get("source_requirement_chunk_ids") or []
    normalized = dict(case)
    normalized["linked_requirement"] = req_id
    normalized["source_requirement_chunk_ids"] = list(chunk_ids)
    normalized["module"] = normalized.get("module") or requirement.get("module")
    normalized.setdefault("priority", "medium")
    normalized.setdefault("test_type", "positive")
    return normalized


def _context_block(state: dict[str, Any]) -> str:
    bugs = state.get("retrieved_bugs") or []
    tcs = state.get("retrieved_tcs") or []
    rag_instruction = (
        RAG_INSTRUCTION_REQUIRED if (bugs or tcs) else RAG_INSTRUCTION_EMPTY
    )
    return CONTEXT_BLOCK.format(
        tc_lines=tc_lines(tcs),
        bug_lines=bug_lines(bugs),
        rag_instruction=rag_instruction,
    )


def _quotas_for_rules(
    rules: list[dict[str, Any]],
    level: str,
    gaps: list[dict[str, Any]] | None,
) -> dict[str, dict[str, int]]:
    """rule_id -> {test_type: count} for this generation pass."""
    from agent.exhaustiveness import quotas_for_level

    base = quotas_for_level(level)
    out: dict[str, dict[str, int]] = {}
    if gaps:
        for g in gaps:
            rid = g.get("rule_id", "")
            t = g.get("test_type", "")
            if not rid or not t:
                continue
            out.setdefault(rid, {})
            out[rid][t] = out[rid].get(t, 0) + int(g.get("needed", 0))
        return out

    for r in rules:
        rid = r.get("rule_id", "")
        if rid:
            out[rid] = {k: v for k, v in base.items() if v > 0}
    return out


def _batch_spec_from_quotas(
    rules: list[dict[str, Any]],
    rule_quotas: dict[str, dict[str, int]],
) -> str:
    lines: list[str] = []
    rules_by_id = {r.get("rule_id"): r for r in rules}
    for rid, quotas in rule_quotas.items():
        r = rules_by_id.get(rid, {})
        parts = [f"{t}: {n}" for t, n in quotas.items() if n > 0]
        lines.append(f"- {rid} ({r.get('summary', '')}): {', '.join(parts)}")
    return "\n".join(lines)


def _rule_history_lines(
    rule: dict[str, Any],
    bugs_by_id: dict[str, dict[str, Any]],
    tcs_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    """Render per-rule retrieved bugs/TCs as prompt lines."""
    bug_ids = rule.get("retrieved_bug_ids") or []
    tc_ids = rule.get("retrieved_tc_ids") or []
    lines: list[str] = []

    if bug_ids:
        lines.append("Retrieved bug reports (same-scope or semantically related):")
        for bid in bug_ids:
            b = bugs_by_id.get(str(bid))
            if not b:
                continue
            sim = b.get("similarity")
            sim_s = f" sim={float(sim):.2f}" if sim is not None else ""
            comp = (b.get("component") or "").strip()
            comp_s = f" component={comp}" if comp else ""
            desc = (b.get("description") or "").replace("\n", " ")[:280]
            lines.append(
                f"- bug_id={bid}{sim_s}{comp_s} :: {b.get('title')} - {desc}"
            )

    if tc_ids:
        lines.append("Retrieved existing test cases (same-scope or semantically related):")
        for tid in tc_ids:
            t = tcs_by_id.get(str(tid))
            if not t:
                continue
            sim = t.get("similarity")
            sim_s = f" sim={float(sim):.2f}" if sim is not None else ""
            desc = (t.get("description") or "").replace("\n", " ")[:200]
            lines.append(f"- tc_id={tid}{sim_s} :: {t.get('title')} - {desc}")

    if not bug_ids and not tc_ids:
        lines.append("Retrieved history: (none)")

    return lines


def _rule_block(
    rule: dict[str, Any],
    quotas: dict[str, int],
    bugs_by_id: dict[str, dict[str, Any]],
    tcs_by_id: dict[str, dict[str, Any]],
    project_index: dict[str, list[dict[str, Any]]] | None = None,
    regen_feedback: dict[str, list[str]] | None = None,
) -> str:
    rid = rule.get("rule_id", "")
    scope = (rule.get("screen") or "General").strip()
    module = (rule.get("module") or "").strip()
    summary = rule.get("summary", "")
    detail = (rule.get("detail") or "")[:400]
    chunk_ids = ", ".join(rule.get("source_requirement_chunk_ids") or []) or "(none)"
    quota_parts = [f"{t}: {n}" for t, n in quotas.items() if n > 0]
    header_extras: list[str] = [f"scope={scope}"]
    if module:
        header_extras.append(f"module={module}")
    header = f"### {rid} - {summary} ({', '.join(header_extras)})"

    lines = [
        header,
        f"Detail: {detail}" if detail else "Detail: (none)",
        f"Allowed source_requirement_chunk_ids: {chunk_ids}",
        f"Quotas: {', '.join(quota_parts) if quota_parts else '(none)'}",
    ]
    if project_index is not None:
        constraint_block = format_constraints_for_prompt(
            constraints_for_rule(rule, project_index=project_index)
        )
        if constraint_block:
            lines.append(constraint_block)
    feedback = (regen_feedback or {}).get(str(rid), [])
    if feedback:
        lines.append("Prior attempt feedback (do not repeat these mistakes):")
        lines.extend(f"- {note}" for note in feedback[:5])
    lines.extend(_rule_history_lines(rule, bugs_by_id, tcs_by_id))
    return "\n".join(lines)


def generate_combined_batch(
    rules: list[dict[str, Any]],
    state: dict[str, Any],
    gaps: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """One LLM call for all test types in the batch, with per-rule history blocks."""
    level = state.get("exhaustiveness_level") or "standard"
    profile = get_profile(level)
    rule_quotas = _quotas_for_rules(rules, level, gaps)
    if not rule_quotas:
        return []

    batch_rules = [r for r in rules if r.get("rule_id") in rule_quotas]
    if not batch_rules:
        return []

    bugs_by_id = {
        str(b.get("id")): b for b in (state.get("retrieved_bugs") or [])
    }
    tcs_by_id = {
        str(t.get("id")): t for t in (state.get("retrieved_tcs") or [])
    }
    all_rules = list(state.get("atomic_rules") or rules)
    project_index = build_project_constraint_index(all_rules)
    regen_feedback = dict(state.get("regen_feedback") or {})

    rule_blocks = "\n\n".join(
        _rule_block(
            r,
            rule_quotas[r["rule_id"]],
            bugs_by_id,
            tcs_by_id,
            project_index,
            regen_feedback,
        )
        for r in batch_rules
    )

    user = COMBINED_USER.format(
        module_hint=state.get("module_hint") or "(none)",
        level_label=profile["label"],
        rule_blocks=rule_blocks,
    )
    llm = get_chat_model()
    structured = llm.with_structured_output(TestCasesBatch)
    result: TestCasesBatch = structured.invoke(
        [SystemMessage(content=COMBINED_SYSTEM), HumanMessage(content=user)]
    )
    cases = _cases_to_dicts(result.test_cases)
    if len(batch_rules) == 1:
        return [_normalize_generated_case(c, batch_rules[0]) for c in cases]
    return cases


def generate_batch(
    *,
    agent: str,
    rules: list[dict[str, Any]],
    type_quotas: dict[str, int],
    state: dict[str, Any],
    system_tpl: str,
    user_tpl: str,
) -> list[dict[str, Any]]:
    if not rules or not any(type_quotas.get(t, 0) > 0 for t in type_quotas):
        return []

    level = state.get("exhaustiveness_level") or "standard"
    profile = get_profile(level)
    ctx = _context_block(state)
    batch_spec = _batch_spec_lines(rules, type_quotas)
    user = user_tpl.format(
        module_hint=state.get("module_hint") or "(none)",
        level_label=profile["label"],
        context_block=ctx,
        batch_spec=batch_spec,
    )
    sys = system_tpl

    llm = get_chat_model()
    structured = llm.with_structured_output(TestCasesBatch)
    result: TestCasesBatch = structured.invoke(
        [SystemMessage(content=sys), HumanMessage(content=user)]
    )
    return _cases_to_dicts(result.test_cases)


def generate_happy_batch(
    rules: list[dict[str, Any]],
    gaps: list[dict[str, Any]] | None,
    state: dict[str, Any],
) -> list[dict[str, Any]]:
    """Generate positive cases; use gap counts on regen, else profile quotas."""
    from agent.exhaustiveness import quotas_for_level

    level = state.get("exhaustiveness_level") or "standard"
    base = quotas_for_level(level)
    type_quotas = {"positive": base.get("positive", 0)}

    if gaps:
        rules_by_id = {r["rule_id"]: r for r in rules}
        gap_quotas: dict[str, int] = {}
        for g in gaps:
            if g.get("test_type") != "positive":
                continue
            rid = g["rule_id"]
            gap_quotas[rid] = gap_quotas.get(rid, 0) + int(g.get("needed", 0))
        all_cases: list[dict[str, Any]] = []
        for rid, count in gap_quotas.items():
            if rid not in rules_by_id or count <= 0:
                continue
            all_cases.extend(
                generate_batch(
                    agent="happy_path",
                    rules=[rules_by_id[rid]],
                    type_quotas={"positive": count},
                    state=state,
                    system_tpl=HAPPY_PATH_SYSTEM,
                    user_tpl=HAPPY_PATH_USER,
                )
            )
        return all_cases

    return generate_batch(
        agent="happy_path",
        rules=rules,
        type_quotas=type_quotas,
        state=state,
        system_tpl=HAPPY_PATH_SYSTEM,
        user_tpl=HAPPY_PATH_USER,
    )


def generate_destructive_batch(
    rules: list[dict[str, Any]],
    gaps: list[dict[str, Any]] | None,
    state: dict[str, Any],
) -> list[dict[str, Any]]:
    from agent.exhaustiveness import DESTRUCTIVE_TYPES, quotas_for_level

    level = state.get("exhaustiveness_level") or "standard"
    base = quotas_for_level(level)
    type_quotas = {t: base[t] for t in DESTRUCTIVE_TYPES if base.get(t, 0) > 0}

    if gaps:
        rules_by_id = {r["rule_id"]: r for r in rules}
        rules_with_gaps: dict[str, dict[str, int]] = {}
        for g in gaps:
            t = g.get("test_type")
            if t not in DESTRUCTIVE_TYPES:
                continue
            rid = g["rule_id"]
            rules_with_gaps.setdefault(rid, {})
            rules_with_gaps[rid][t] = rules_with_gaps[rid].get(t, 0) + int(g.get("needed", 0))
        all_cases: list[dict[str, Any]] = []
        for rid, per_type in rules_with_gaps.items():
            if rid not in rules_by_id:
                continue
            batch_cases = generate_batch(
                agent="destructive",
                rules=[rules_by_id[rid]],
                type_quotas=per_type,
                state=state,
                system_tpl=DESTRUCTIVE_SYSTEM,
                user_tpl=DESTRUCTIVE_USER,
            )
            all_cases.extend(batch_cases)
        return all_cases

    return generate_batch(
        agent="destructive",
        rules=rules,
        type_quotas=type_quotas,
        state=state,
        system_tpl=DESTRUCTIVE_SYSTEM,
        user_tpl=DESTRUCTIVE_USER,
    )
