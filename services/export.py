"""Export test cases to CSV or Excel."""

from __future__ import annotations

import io
from typing import Any

import pandas as pd

from services.project_ui import format_numbered_steps_text, normalize_test_steps


def _title_case_type(value: Any) -> str:
    text = str(value or "").strip()
    return text[:1].upper() + text[1:].lower() if text else ""


def test_cases_to_dataframe(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    flat: list[dict[str, Any]] = []
    for r in rows:
        steps = r.get("steps")
        steps_str = (
            format_numbered_steps_text(steps)
            if normalize_test_steps(steps)
            else str(steps or "")
        )
        flat.append(
            {
                "TestCase_ID": r.get("testcase_id") or r.get("id"),
                "Requirement_ID": r.get("linked_requirement"),
                "Test_Case_Type": _title_case_type(r.get("test_type")),
                "Test_Scenario": r.get("title"),
                "Preconditions": r.get("preconditions"),
                "Test_Steps": steps_str,
                "Expected_Result": r.get("expected_result"),
                "Priority": _title_case_type(r.get("priority")),
                "Module": r.get("module"),
            }
        )
    return pd.DataFrame(flat)


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="test_cases")
    return buf.getvalue()
