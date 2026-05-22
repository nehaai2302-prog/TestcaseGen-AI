"""Extract plain text from PDF, DOCX, and TXT uploads.

For PDFs and DOCX, tables are detected and any row that begins with a
requirement ID (FR-1.1, BND-001, REQ-12, 1.2.3, ...) is flattened into a
single line of the form ``ID: rest`` so the downstream requirement splitter
can pick it up. Non-requirement tables are rendered generically as
``cell | cell | cell`` lines and remain available to embedding/RAG but won't
falsely match as new requirements.
"""

from __future__ import annotations

import io
import logging
import re
from pathlib import Path
from typing import Iterator

import pdfplumber
from docx import Document as DocxDocument
from docx.document import Document as _DocxDocument
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader

log = logging.getLogger(__name__)

# Detects a requirement ID at the START of a table cell so we can render the
# row as "ID: rest" and let the splitter recognise it. Supports prefix-style
# (FR-1.1, BND-001, US-103) and dotted-numeric (1.2.3).
_TABLE_REQ_ID_RE = re.compile(
    r"""
    ^[ \t]*
    (?P<id>
        [A-Z]{2,10}[-_ ]?\d+(?:\.\d+)*   # FR-1.1, BND-001, NFR_12 ...
      | \d+(?:\.\d+){1,}                 # 1.2.3 (>=2 parts)
    )
    \b
    """,
    re.VERBOSE,
)


def parse_uploaded_file(name: str, data: bytes) -> str:
    """Return UTF-8 text from file bytes based on extension."""
    suffix = Path(name).suffix.lower()
    if suffix == ".pdf":
        return _parse_pdf(data)
    if suffix in (".docx",):
        return _parse_docx(data)
    if suffix in (".txt", ".md"):
        return data.decode("utf-8", errors="replace")
    raise ValueError(f"Unsupported file type: {suffix}. Use .pdf, .docx, or .txt")


# ---------------------------------------------------------------------------
# Shared: row -> text rendering
# ---------------------------------------------------------------------------

def _clean_cell(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _normalize_rows(rows: list[list[object]]) -> list[list[str]]:
    """Clean cells, drop empty cells, collapse adjacent merge duplicates, drop empty rows."""
    out: list[list[str]] = []
    for row in rows or []:
        cleaned: list[str] = []
        last: str | None = None
        for cell in row:
            text = _clean_cell(cell)
            if not text:
                last = None
                continue
            if text == last:
                continue
            cleaned.append(text)
            last = text
        if cleaned:
            out.append(cleaned)
    return out


def _format_requirements_row(cells: list[str]) -> str:
    """Render a data row whose first cell starts with a requirement ID."""
    first = cells[0]
    match = _TABLE_REQ_ID_RE.match(first)
    if not match:
        return " | ".join(cells)
    req_id = match.group("id")
    leftover_first = first[match.end():].strip(" \t,:;-\u2014")
    rest_parts: list[str] = []
    if leftover_first:
        rest_parts.append(leftover_first)
    rest_parts.extend(cells[1:])
    body = " \u2014 ".join(rest_parts)
    return f"{req_id}: {body}" if body else f"{req_id}:"


def _rows_to_text(rows: list[list[str]]) -> str:
    """Convert normalized rows to newline-separated lines.

    If any data row starts with a requirement ID, treat the table as a
    requirements table: drop an optional header row and flatten each data row
    as "REQ-ID: rest". Otherwise render rows generically.
    """
    if not rows:
        return ""
    has_req_rows = any(_TABLE_REQ_ID_RE.match(row[0]) for row in rows)
    if has_req_rows and not _TABLE_REQ_ID_RE.match(rows[0][0]):
        rows = rows[1:]
    lines: list[str] = []
    for cells in rows:
        if _TABLE_REQ_ID_RE.match(cells[0]):
            lines.append(_format_requirements_row(cells))
        else:
            lines.append(" | ".join(cells))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------

_P_TAG = qn("w:p")
_TBL_TAG = qn("w:tbl")


def _is_inside_table(element) -> bool:
    parent = element.getparent()
    while parent is not None:
        if parent.tag == _TBL_TAG:
            return True
        parent = parent.getparent()
    return False


def _iter_block_items(doc: _DocxDocument) -> Iterator[Paragraph | Table]:
    """Yield top-level paragraphs AND tables in document order.

    Recursive descendant scan so tables wrapped inside content controls
    (`w:sdt` -> `w:sdtContent`), text boxes, or other block wrappers are still
    picked up. Paragraphs/tables nested inside another table are skipped
    because their text is reached through the outer `Table` instance.
    """
    body = doc.element.body
    for element in body.iter(_P_TAG, _TBL_TAG):
        if _is_inside_table(element):
            continue
        if element.tag == _P_TAG:
            yield Paragraph(element, doc)
        else:
            yield Table(element, doc)


def _docx_table_rows(table: Table) -> list[list[str]]:
    raw: list[list[object]] = [
        [cell.text for cell in row.cells] for row in table.rows
    ]
    return _normalize_rows(raw)


def _parse_docx(data: bytes) -> str:
    doc = DocxDocument(io.BytesIO(data))
    parts: list[str] = []
    for block in _iter_block_items(doc):
        if isinstance(block, Paragraph):
            text = block.text.strip()
            if text:
                parts.append(text)
        elif isinstance(block, Table):
            table_text = _rows_to_text(_docx_table_rows(block))
            if table_text:
                parts.append(table_text)
    return "\n".join(parts).strip()


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

def _pypdf_fallback(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    parts: list[str] = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n\n".join(parts).strip()


def _extract_pdf_page(page) -> str:
    """Extract text + flattened tables from one PDF page, in vertical order.

    Slices the page into horizontal stripes around each detected table so the
    output preserves reading order: text above table -> table -> text below.
    """
    try:
        tables = page.find_tables() or []
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("pdfplumber.find_tables failed on page %s: %s", page.page_number, exc)
        tables = []

    tables = sorted(tables, key=lambda t: t.bbox[1])  # sort by top y

    if not tables:
        return page.extract_text() or ""

    page_width = page.width
    page_height = page.height
    parts: list[str] = []
    cursor_y = 0.0

    for tbl in tables:
        x0, top, x1, bottom = tbl.bbox
        if top > cursor_y:
            try:
                stripe = page.within_bbox((0, cursor_y, page_width, top))
                stripe_text = stripe.extract_text() or ""
            except Exception:
                stripe_text = ""
            if stripe_text.strip():
                parts.append(stripe_text)
        try:
            raw_rows = tbl.extract() or []
        except Exception as exc:  # pragma: no cover - defensive
            log.warning(
                "pdfplumber failed to extract a table on page %s: %s",
                page.page_number,
                exc,
            )
            raw_rows = []
        table_text = _rows_to_text(_normalize_rows(raw_rows))
        if table_text:
            parts.append(table_text)
        cursor_y = max(cursor_y, bottom)

    if cursor_y < page_height:
        try:
            stripe = page.within_bbox((0, cursor_y, page_width, page_height))
            stripe_text = stripe.extract_text() or ""
        except Exception:
            stripe_text = ""
        if stripe_text.strip():
            parts.append(stripe_text)

    return "\n".join(parts)


def _parse_pdf(data: bytes) -> str:
    """Extract text from a PDF, flattening native tables into 'ID: rest' lines."""
    try:
        parts: list[str] = []
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                try:
                    page_text = _extract_pdf_page(page)
                except Exception as exc:
                    log.warning(
                        "pdfplumber failed on page %s, falling back to flat text: %s",
                        page.page_number,
                        exc,
                    )
                    page_text = page.extract_text() or ""
                if page_text.strip():
                    parts.append(page_text)
        text = "\n\n".join(parts).strip()
        if text:
            return text
    except Exception as exc:
        log.warning(
            "pdfplumber could not open the document, falling back to pypdf: %s",
            exc,
        )
    return _pypdf_fallback(data)
