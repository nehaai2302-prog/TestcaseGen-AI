"""Supabase / Postgres data access for TestCraft AI."""

from __future__ import annotations

import hashlib
import os
from typing import Any

from supabase import Client, create_client

from services.project_ui import MODULE_NONE_SENTINEL


def _filter_rows_by_module(
    rows: list[dict[str, Any]],
    module_filter: str | None,
) -> list[dict[str, Any]]:
    if module_filter is None:
        return rows
    if module_filter == MODULE_NONE_SENTINEL:
        return [r for r in rows if not (r.get("module") or "").strip()]
    return [r for r in rows if (r.get("module") or "").strip() == module_filter]


def _get_client() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
    return create_client(url, key)


class SupabaseRepo:
    """Thin repository around supabase-py table and RPC calls."""

    def __init__(self, client: Client | None = None) -> None:
        self._client = client or _get_client()

    @property
    def client(self) -> Client:
        return self._client

    # --- Projects ---

    def create_project(self, name: str, description: str | None = None) -> dict[str, Any]:
        row = {"name": name, "description": description or ""}
        res = self._client.table("projects").insert(row).execute()
        return res.data[0]

    def list_projects(self) -> list[dict[str, Any]]:
        res = (
            self._client.table("projects")
            .select("id,name,description,created_at")
            .order("created_at", desc=True)
            .execute()
        )
        return res.data or []

    def delete_project(self, project_id: str) -> None:
        self._client.table("projects").delete().eq("id", project_id).execute()

    # --- Requirements ---

    def delete_requirements_for_document(self, project_id: str, document_name: str) -> None:
        self._client.table("requirements").delete().eq("project_id", project_id).eq(
            "document_name", document_name
        ).execute()

    def insert_requirement_chunks(
        self,
        project_id: str,
        document_name: str,
        chunks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Each row dict: requirement_id, chunk_text, embedding (list[float]), module optional."""
        if not chunks:
            return []
        res = self._client.table("requirements").insert(chunks).execute()
        return res.data or []

    def list_requirements_for_document(
        self, project_id: str, document_name: str
    ) -> list[dict[str, Any]]:
        res = (
            self._client.table("requirements")
            .select(
                "id,project_id,document_name,chunk_index,chunk_text,"
                "requirement_id,is_synthetic_requirement,module,created_at"
            )
            .eq("project_id", project_id)
            .eq("document_name", document_name)
            .order("chunk_index")
            .execute()
        )
        return res.data or []

    # --- Match RPCs (pgvector) ---

    def match_requirements(
        self,
        project_id: str,
        query_embedding: list[float],
        match_threshold: float = 0.2,
        match_count: int = 12,
    ) -> list[dict[str, Any]]:
        res = self._client.rpc(
            "match_requirements",
            {
                "query_embedding": query_embedding,
                "match_threshold": match_threshold,
                "match_count": match_count,
                "p_project_id": project_id,
            },
        ).execute()
        return res.data or []

    def match_test_cases(
        self,
        project_id: str,
        query_embedding: list[float],
        match_threshold: float = 0.2,
        match_count: int = 15,
    ) -> list[dict[str, Any]]:
        res = self._client.rpc(
            "match_test_cases",
            {
                "query_embedding": query_embedding,
                "match_threshold": match_threshold,
                "match_count": match_count,
                "p_project_id": project_id,
            },
        ).execute()
        return res.data or []

    def match_bug_reports(
        self,
        project_id: str,
        query_embedding: list[float],
        match_threshold: float = 0.2,
        match_count: int = 15,
    ) -> list[dict[str, Any]]:
        res = self._client.rpc(
            "match_bug_reports",
            {
                "query_embedding": query_embedding,
                "match_threshold": match_threshold,
                "match_count": match_count,
                "p_project_id": project_id,
            },
        ).execute()
        return res.data or []

    # --- Bugs ---

    def insert_bug_reports(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not rows:
            return []
        res = self._client.table("bug_reports").insert(rows).execute()
        return res.data or []

    def list_bug_reports(self, project_id: str, limit: int = 500) -> list[dict[str, Any]]:
        res = (
            self._client.table("bug_reports")
            .select("*")
            .eq("project_id", project_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []

    # --- Test cases ---

    def insert_test_cases(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not rows:
            return []
        res = self._client.table("test_cases").insert(rows).execute()
        return res.data or []

    def list_test_cases(
        self,
        project_id: str,
        test_type: str | None = None,
        priority: str | None = None,
        module: str | None = None,
        source: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        q = self._client.table("test_cases").select("*").eq("project_id", project_id)
        if test_type:
            q = q.eq("test_type", test_type)
        if priority:
            q = q.eq("priority", priority)
        if module:
            q = q.eq("module", module)
        if source:
            q = q.eq("source", source)
        res = q.order("created_at", desc=True).limit(limit).execute()
        return res.data or []

    def count_test_cases(self, project_id: str) -> int:
        res = (
            self._client.table("test_cases")
            .select("id", count="exact")
            .eq("project_id", project_id)
            .execute()
        )
        return res.count or 0

    def get_test_case_traceability(
        self,
        project_id: str,
        module_filter: str | None = None,
    ) -> dict[str, Any]:
        """Aggregate test cases by linked_requirement; optional module slice."""
        res = (
            self._client.table("test_cases")
            .select("linked_requirement,source,module")
            .eq("project_id", project_id)
            .execute()
        )
        all_rows = res.data or []
        project_total = len(all_rows)
        rows = _filter_rows_by_module(all_rows, module_filter)
        generated = 0
        imported = 0
        by_req: dict[str, int] = {}
        unlinked = 0

        for row in rows:
            src = (row.get("source") or "").strip().lower()
            if src == "imported":
                imported += 1
            else:
                generated += 1

            req = (row.get("linked_requirement") or "").strip()
            if not req:
                unlinked += 1
                continue
            by_req[req] = by_req.get(req, 0) + 1

        by_requirement = [
            {"linked_requirement": rid, "test_case_count": count}
            for rid, count in sorted(by_req.items(), key=lambda x: x[0].lower())
        ]
        return {
            "total": len(rows),
            "project_total": project_total,
            "generated": generated,
            "imported": imported,
            "unlinked": unlinked,
            "distinct_requirements": len(by_req),
            "by_requirement": by_requirement,
        }

    def count_bug_reports(self, project_id: str) -> int:
        res = (
            self._client.table("bug_reports")
            .select("id", count="exact")
            .eq("project_id", project_id)
            .execute()
        )
        return res.count or 0

    def count_requirements(self, project_id: str) -> int:
        res = (
            self._client.table("requirements")
            .select("id", count="exact")
            .eq("project_id", project_id)
            .execute()
        )
        return res.count or 0

    # --- Generation history ---

    def insert_generation_history(self, row: dict[str, Any]) -> dict[str, Any]:
        res = self._client.table("generation_history").insert(row).execute()
        return (res.data or [row])[0]

    def list_generation_history(self, project_id: str, limit: int = 20) -> list[dict[str, Any]]:
        res = (
            self._client.table("generation_history")
            .select("*")
            .eq("project_id", project_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]
