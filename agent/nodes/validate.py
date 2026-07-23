"""Mark near-duplicates: batch title/semantic pass, then library similarity."""

from __future__ import annotations

import hashlib
import os
import re
from typing import Any

from agent.cross_req_dedup import cross_requirement_scenario_dedup
from agent.state import TestGenState
from services.embeddings import embed_texts, get_embeddings_model
from services.supabase_repo import SupabaseRepo


def _norm_title(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _norm_text(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _verbatim_fingerprint(case: dict[str, Any]) -> str:
    """Fingerprint steps + expected result (titles may differ)."""
    steps = case.get("steps") or []
    if isinstance(steps, list):
        steps_str = "\n".join(str(s) for s in steps)
    else:
        steps_str = str(steps)
    blob = f"{steps_str}\n{case.get('expected_result', '')}"
    return hashlib.sha256(_norm_text(blob).encode()).hexdigest()


def _case_blob(case: dict[str, Any]) -> str:
    title = case.get("title") or ""
    steps = case.get("steps") or []
    if isinstance(steps, list):
        steps_str = "\n".join(str(s) for s in steps)
    else:
        steps_str = str(steps)
    return f"{title}\n{steps_str}\n{case.get('expected_result', '')}"


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Dot product for L2-normalized OpenAI embedding vectors."""
    return sum(x * y for x, y in zip(a, b))


def batch_semantic_dedup(
    cases: list[dict[str, Any]],
    vectors: list[list[float]],
    *,
    threshold: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Greedy clustering: keep first case per semantic cluster in input order."""
    kept: list[dict[str, Any]] = []
    kept_vectors: list[list[float]] = []
    duplicates: list[dict[str, Any]] = []

    for case, vector in zip(cases, vectors):
        match_title: str | None = None
        match_similarity: float | None = None
        for prior_case, prior_vector in zip(kept, kept_vectors):
            sim = cosine_similarity(vector, prior_vector)
            if sim >= threshold:
                match_title = prior_case.get("title")
                match_similarity = sim
                break
        if match_title:
            duplicates.append(
                {
                    **case,
                    "is_duplicate": True,
                    "duplicate_reason": "batch_semantic_duplicate",
                    "similar_to_title": match_title,
                    "similarity": match_similarity,
                }
            )
            continue
        kept.append(case)
        kept_vectors.append(vector)

    return kept, duplicates


def validate_dedup(state: TestGenState, repo: SupabaseRepo) -> dict[str, Any]:
    project_id = state["project_id"]
    generated = list(state.get("generated_cases") or [])
    if not generated:
        return {
            "validated_cases": [],
            "duplicates": [],
            "batch_dedup_stats": {
                "input_cases": 0,
                "kept": 0,
                "removed_title": 0,
                "removed_verbatim": 0,
                "removed_cross_req": 0,
                "removed_semantic": 0,
                "removed_library": 0,
            },
            "current_step": "validate_dedup",
        }

    # On incomplete-requirement regen, keep previously accepted cases as-is and
    # only dedup the newly generated drafts (avoid library self-matches).
    prior_kept = [c for c in generated if c.get("_already_persisted")]
    fresh = [c for c in generated if not c.get("_already_persisted")]
    if state.get("regen_mode") and prior_kept and not fresh:
        return {
            "validated_cases": prior_kept,
            "duplicates": [],
            "batch_dedup_stats": {
                "input_cases": len(generated),
                "kept": len(prior_kept),
                "removed_title": 0,
                "removed_verbatim": 0,
                "removed_cross_req": 0,
                "removed_semantic": 0,
                "removed_library": 0,
            },
            "current_step": "validate_dedup",
        }

    work = fresh if state.get("regen_mode") and prior_kept else generated

    emb_model = get_embeddings_model()
    lib_threshold = float(os.environ.get("DEDUP_SIMILARITY_THRESHOLD", "0.88"))
    batch_threshold = float(os.environ.get("BATCH_DEDUP_SIMILARITY_THRESHOLD", "0.90"))
    match_k = int(os.environ.get("DEDUP_MATCH_K", "5"))

    duplicates: list[dict[str, Any]] = []
    seen_titles: dict[str, str] = {}
    removed_title = 0

    after_title: list[dict[str, Any]] = []
    title_blobs: list[str] = []
    for case in work:
        title = case.get("title") or ""
        nt = _norm_title(title)
        if nt in seen_titles:
            removed_title += 1
            duplicates.append(
                {
                    **case,
                    "duplicate_reason": "batch_title_duplicate",
                    "similar_to_title": seen_titles[nt],
                }
            )
            continue
        # Also avoid title clash with already-kept prior cases during regen
        if state.get("regen_mode") and any(
            _norm_title(str(p.get("title") or "")) == nt for p in prior_kept
        ):
            removed_title += 1
            duplicates.append(
                {
                    **case,
                    "duplicate_reason": "batch_title_duplicate",
                    "similar_to_title": title,
                }
            )
            continue
        seen_titles[nt] = title
        after_title.append(case)
        title_blobs.append(_case_blob(case))

    removed_verbatim = 0
    after_verbatim: list[dict[str, Any]] = []
    seen_verbatim: dict[str, str] = {
        _verbatim_fingerprint(p): str(p.get("title") or "") for p in prior_kept
    }
    for case in after_title:
        fp = _verbatim_fingerprint(case)
        if fp in seen_verbatim:
            removed_verbatim += 1
            duplicates.append(
                {
                    **case,
                    "duplicate_reason": "batch_verbatim_duplicate",
                    "similar_to_title": seen_verbatim[fp],
                }
            )
            continue
        seen_verbatim[fp] = str(case.get("title") or "")
        after_verbatim.append(case)

    # Cross-requirement scenario dedup: shared error codes / identical failure
    # modes across different linked_requirement values (not general semantic).
    after_cross, cross_dups = cross_requirement_scenario_dedup(
        after_verbatim,
        seed_cases=prior_kept if state.get("regen_mode") else None,
    )
    removed_cross_req = len(cross_dups)
    duplicates.extend(cross_dups)

    # Semantic dedup must be scoped to avoid dropping valid Smoke (positive + negative)
    # pairs or removing cases that belong to different requirements.
    #
    # Scope: (linked_requirement, test_type)
    removed_semantic = 0
    after_semantic: list[dict[str, Any]] = []
    if after_cross:
        groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
        group_order: list[tuple[str, str]] = []
        for case in after_cross:
            req = (case.get("linked_requirement") or "").strip()
            ttype = (case.get("test_type") or "positive").strip().lower()
            key = (req, ttype)
            if key not in groups:
                groups[key] = []
                group_order.append(key)
            groups[key].append(case)

        for key in group_order:
            group_cases = groups.get(key) or []
            if len(group_cases) <= 1:
                after_semantic.extend(group_cases)
                continue

            group_blobs = [_case_blob(c) for c in group_cases]
            group_vectors = embed_texts(emb_model, group_blobs)
            kept_group, semantic_dups = batch_semantic_dedup(
                group_cases, group_vectors, threshold=batch_threshold
            )
            removed_semantic += len(semantic_dups)
            duplicates.extend(semantic_dups)
            after_semantic.extend(kept_group)

    validated: list[dict[str, Any]] = []
    removed_library = 0
    if after_semantic:
        lib_blobs = [_case_blob(case) for case in after_semantic]
        lib_vectors = embed_texts(emb_model, lib_blobs)
        for case, qe in zip(after_semantic, lib_vectors):
            hits = repo.match_test_cases(
                project_id, qe, match_threshold=0.1, match_count=match_k
            )
            dup_hit = None
            for h in hits:
                sim = float(h.get("similarity") or 0)
                if sim >= lib_threshold:
                    dup_hit = h
                    break

            if dup_hit:
                removed_library += 1
                duplicates.append(
                    {
                        **case,
                        "is_duplicate": True,
                        "similar_to_id": str(dup_hit.get("id") or ""),
                        "similar_to_title": dup_hit.get("title"),
                        "similar_to_test_type": dup_hit.get("test_type"),
                        "duplicate_reason": f"library_similarity={dup_hit.get('similarity')}",
                    }
                )
            else:
                validated.append(case)

    if state.get("regen_mode") and prior_kept:
        validated = prior_kept + validated

    stats = {
        "input_cases": len(generated),
        "kept": len(validated),
        "removed_title": removed_title,
        "removed_verbatim": removed_verbatim,
        "removed_cross_req": removed_cross_req,
        "removed_semantic": removed_semantic,
        "removed_library": removed_library,
    }

    return {
        "validated_cases": validated,
        "duplicates": duplicates,
        "batch_dedup_stats": stats,
        "current_step": "validate_dedup",
    }
