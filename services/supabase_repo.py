"""Supabase / Postgres data access for QAWeaver AI."""

from __future__ import annotations

import hashlib
import os
from typing import Any

from supabase import Client, create_client

from services.project_ui import MODULE_NONE_SENTINEL


class DuplicateProjectNameError(RuntimeError):
    """Raised when creating a project with an existing normalized name."""


def _filter_rows_by_module(
    rows: list[dict[str, Any]],
    module_filter: str | None,
) -> list[dict[str, Any]]:
    if module_filter is None:
        return rows
    if module_filter == MODULE_NONE_SENTINEL:
        return [r for r in rows if not (r.get("module") or "").strip()]
    return [r for r in rows if (r.get("module") or "").strip() == module_filter]


def _get_service_client() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
    return create_client(url, key)


class SupabaseRepo:
    """Thin repository around supabase-py table and RPC calls."""

    def __init__(self, client: Client | None = None, user_id: str | None = None) -> None:
        self._client = client or _get_service_client()
        self._user_id = user_id

    @property
    def user_id(self) -> str | None:
        return self._user_id

    @property
    def client(self) -> Client:
        return self._client

    def get_demo_video_url(self) -> str | None:
        # Private Storage signed URLs require the service role — never the user JWT.
        return get_demo_video_url()

    # --- Projects ---

    def create_project(self, name: str, description: str | None = None) -> dict[str, Any]:
        if not self._user_id:
            raise RuntimeError("Cannot create a project without a signed-in user.")
        row = {
            "name": name,
            "description": description or "",
            "user_id": self._user_id,
        }
        try:
            res = self._client.table("projects").insert(row).execute()
            return res.data[0]
        except Exception as e:
            msg = str(e).lower()
            if "duplicate key" in msg and (
                "ux_projects_user_name_norm" in msg or "ux_projects_name_norm" in msg
            ):
                raise DuplicateProjectNameError(
                    "A project with this name already exists."
                ) from e
            raise

    def list_projects(self) -> list[dict[str, Any]]:
        res = (
            self._client.table("projects")
            .select("id,name,description,created_at,user_id")
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
                "id,project_id,document_name,chunk_index,chunk_text,content_hash,"
                "requirement_id,is_synthetic_requirement,module,created_at"
            )
            .eq("project_id", project_id)
            .eq("document_name", document_name)
            .order("chunk_index")
            .execute()
        )
        return res.data or []

    def list_requirement_summaries_for_project(
        self, project_id: str
    ) -> list[dict[str, Any]]:
        """Distinct requirement IDs for a project, sorted by requirement_id.

        Each summary includes document_name, module, and a short text preview from
        the first chunk for that ID.
        """
        res = (
            self._client.table("requirements")
            .select(
                "id,requirement_id,document_name,chunk_text,chunk_index,module"
            )
            .eq("project_id", project_id)
            .order("requirement_id")
            .order("chunk_index")
            .execute()
        )
        rows = res.data or []
        by_id: dict[str, dict[str, Any]] = {}
        for row in rows:
            rid = (row.get("requirement_id") or "").strip()
            if not rid or rid in by_id:
                continue
            text = " ".join(str(row.get("chunk_text") or "").split())
            preview = text if len(text) <= 120 else text[:120] + "…"
            by_id[rid] = {
                "requirement_id": rid,
                "document_name": row.get("document_name") or "",
                "module": row.get("module") or "",
                "preview": preview,
                "chunk_id": row.get("id"),
            }
        return sorted(by_id.values(), key=lambda r: str(r["requirement_id"]))

    def get_requirement_chunks_by_id(
        self, project_id: str, requirement_id: str
    ) -> list[dict[str, Any]]:
        """All chunks for a requirement ID in this project (ordered by chunk_index)."""
        rid = (requirement_id or "").strip()
        if not rid:
            return []
        res = (
            self._client.table("requirements")
            .select(
                "id,requirement_id,document_name,chunk_index,chunk_text,module,"
                "is_synthetic_requirement"
            )
            .eq("project_id", project_id)
            .eq("requirement_id", rid)
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

    def delete_generated_test_cases_for_requirements(
        self,
        project_id: str,
        requirement_ids: list[str],
    ) -> int:
        """Delete generated (not imported) cases linked to the given requirement IDs.

        Returns the number of rows deleted when the API provides a count; otherwise
        returns the number of IDs requested (best-effort).
        """
        ids = sorted({str(r).strip() for r in requirement_ids if str(r).strip()})
        if not ids:
            return 0
        res = (
            self._client.table("test_cases")
            .delete()
            .eq("project_id", project_id)
            .eq("source", "generated")
            .in_("linked_requirement", ids)
            .execute()
        )
        data = res.data
        if isinstance(data, list):
            return len(data)
        return len(ids)

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
        by_req: dict[str, dict[str, int]] = {}
        unlinked = 0
        unlinked_generated = 0
        unlinked_imported = 0

        for row in rows:
            src = (row.get("source") or "").strip().lower()
            is_imported = src == "imported"
            if is_imported:
                imported += 1
            else:
                generated += 1

            req = (row.get("linked_requirement") or "").strip()
            if not req:
                unlinked += 1
                if is_imported:
                    unlinked_imported += 1
                else:
                    unlinked_generated += 1
                continue
            bucket = by_req.setdefault(
                req, {"generated": 0, "imported": 0, "test_case_count": 0}
            )
            if is_imported:
                bucket["imported"] += 1
            else:
                bucket["generated"] += 1
            bucket["test_case_count"] += 1

        by_requirement = [
            {
                "linked_requirement": rid,
                "test_case_count": counts["test_case_count"],
                "generated": counts["generated"],
                "imported": counts["imported"],
            }
            for rid, counts in sorted(by_req.items(), key=lambda x: x[0].lower())
        ]
        return {
            "total": len(rows),
            "project_total": project_total,
            "generated": generated,
            "imported": imported,
            "unlinked": unlinked,
            "unlinked_generated": unlinked_generated,
            "unlinked_imported": unlinked_imported,
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


def get_demo_video_url(client: Client | None = None) -> str | None:
    """Signed URL for a demo video in private Supabase Storage (regenerated each call).

    Signs with the service-role client by default. User/anon JWTs cannot read a
    private demo bucket (auth made this fail silently and hide the Home link).
    """
    bucket = os.getenv("DEMO_VIDEO_BUCKET", "").strip()
    path = os.getenv("DEMO_VIDEO_PATH", "").strip().lstrip("/")
    if not bucket or not path:
        return None
    ttl = int(os.getenv("DEMO_VIDEO_SIGNED_URL_TTL", "86400"))
    try:
        res = (client or _get_service_client()).storage.from_(bucket).create_signed_url(
            path, ttl
        )
    except Exception:
        return None
    if isinstance(res, dict):
        url = res.get("signedURL") or res.get("signed_url")
        return str(url).strip() if url else None
    signed = getattr(res, "signed_url", None) or getattr(res, "signedURL", None)
    return str(signed).strip() if signed else None


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]
