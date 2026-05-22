"""Mark near-duplicates against existing library using embedding similarity."""

from __future__ import annotations

import os
import re
from typing import Any

from agent.state import TestGenState
from services.embeddings import embed_texts, get_embeddings_model
from services.supabase_repo import SupabaseRepo


def _norm_title(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _case_blob(case: dict[str, Any]) -> str:
    title = case.get("title") or ""
    steps = case.get("steps") or []
    if isinstance(steps, list):
        steps_str = "\n".join(str(s) for s in steps)
    else:
        steps_str = str(steps)
    return f"{title}\n{steps_str}\n{case.get('expected_result', '')}"


def validate_dedup(state: TestGenState, repo: SupabaseRepo) -> dict[str, Any]:
    project_id = state["project_id"]
    generated = list(state.get("generated_cases") or [])
    if not generated:
        return {
            "validated_cases": [],
            "duplicates": [],
            "current_step": "validate_dedup",
        }

    emb_model = get_embeddings_model()
    dup_threshold = float(os.environ.get("DEDUP_SIMILARITY_THRESHOLD", "0.88"))
    match_k = int(os.environ.get("DEDUP_MATCH_K", "5"))

    validated: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    seen_titles: dict[str, str] = {}

    pending: list[tuple[int, dict[str, Any], str]] = []
    for i, case in enumerate(generated):
        title = case.get("title") or ""
        nt = _norm_title(title)
        if nt in seen_titles:
            duplicates.append(
                {
                    **case,
                    "duplicate_reason": "batch_title_duplicate",
                    "similar_to_title": seen_titles[nt],
                }
            )
            continue
        seen_titles[nt] = title
        pending.append((i, case, _case_blob(case)))

    if pending:
        vectors = embed_texts(emb_model, [blob for _, _, blob in pending])
        for (_, case, _), qe in zip(pending, vectors):
            hits = repo.match_test_cases(project_id, qe, match_threshold=0.1, match_count=match_k)
            dup_hit = None
            for h in hits:
                sim = float(h.get("similarity") or 0)
                if sim >= dup_threshold:
                    dup_hit = h
                    break

            if dup_hit:
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

    return {
        "validated_cases": validated,
        "duplicates": duplicates,
        "current_step": "validate_dedup",
    }
