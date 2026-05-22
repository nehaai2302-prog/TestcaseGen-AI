"""Format requirement chunks and RAG context for prompts."""

from __future__ import annotations

from typing import Any


def chunk_lines(chunks: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for c in chunks:
        cid = str(c.get("id", ""))
        idx = c.get("chunk_index", 0)
        req_id = c.get("requirement_id") or ""
        req_part = f" requirement_id={req_id}" if req_id else ""
        text = (c.get("chunk_text") or "").replace("\n", " ")[:800]
        lines.append(f"- id={cid} chunk_index={idx}{req_part} :: {text}")
    return "\n".join(lines) if lines else "- (no chunks)"


def bug_lines(bugs: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for b in bugs:
        bid = str(b.get("id", ""))
        title = b.get("title", "")
        desc = (b.get("description") or "")[:400]
        sim = b.get("similarity")
        sim_s = f" similarity={float(sim):.2f}" if sim is not None else ""
        lines.append(f"- bug_id={bid}{sim_s} :: {title} — {desc}")
    return "\n".join(lines) if lines else "- (none retrieved)"


def tc_lines(tcs: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for t in tcs:
        tid = str(t.get("id", ""))
        title = t.get("title", "")
        desc = (t.get("description") or "")[:300]
        sim = t.get("similarity")
        sim_s = f" similarity={float(sim):.2f}" if sim is not None else ""
        lines.append(f"- tc_id={tid}{sim_s} :: {title} — {desc}")
    return "\n".join(lines) if lines else "- (none retrieved)"


def rules_block(rules: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for r in rules:
        rid = r.get("rule_id", "")
        summary = r.get("summary", "")
        detail = (r.get("detail") or "")[:500]
        chunk_ids = ", ".join(r.get("source_requirement_chunk_ids") or [])
        lines.append(f"- {rid}: {summary}\n  detail: {detail}\n  chunk_ids: {chunk_ids}")
    return "\n".join(lines) if lines else "- (no rules)"
