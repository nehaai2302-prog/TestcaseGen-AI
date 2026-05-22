"""Diagnostic: show what the parser extracts from a real document.

Usage:
    uv run python scripts/debug_parse_doc.py "path/to/your/file.docx"

Prints:
    1. The first ~120 lines of the parsed text (so you can SEE if the
       table rows came through as "BND-001: ...").
    2. The list of requirement IDs the splitter detected.
    3. For docx files: how many top-level tables vs. SDT-wrapped tables
       the file actually contains, so we can tell *where* a table lives
       if it didn't show up.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from repo root or from scripts/.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.chunking import split_requirements  # noqa: E402
from services.document_parser import parse_uploaded_file  # noqa: E402


def _docx_table_summary(path: Path) -> None:
    from docx import Document
    from docx.oxml.ns import qn

    doc = Document(str(path))
    body = doc.element.body
    direct_tables = sum(1 for c in body.iterchildren() if c.tag == qn("w:tbl"))
    all_tables = sum(1 for _ in body.iter(qn("w:tbl")))
    sdt_wrapped = all_tables - direct_tables
    print(
        f"[docx] tables: total={all_tables}  direct-children-of-body={direct_tables}  "
        f"wrapped-in-sdt/textbox/etc={sdt_wrapped}"
    )


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    path = Path(argv[1])
    if not path.exists():
        print(f"File not found: {path}")
        return 2

    data = path.read_bytes()

    if path.suffix.lower() == ".docx":
        _docx_table_summary(path)

    text = parse_uploaded_file(path.name, data)
    lines = text.splitlines()
    print(f"\n[parsed] total lines: {len(lines)}")
    print("---- first 120 lines of parsed text ----")
    for i, line in enumerate(lines[:120], start=1):
        print(f"{i:4d} | {line}")
    print("---- end preview ----")

    splits = split_requirements(text)
    print(f"\n[splitter] detected {len(splits)} requirement(s):")
    for s in splits:
        first_line = s.text.splitlines()[0][:140] if s.text else ""
        marker = " (synthetic)" if s.is_synthetic else ""
        print(f"  {s.requirement_id}{marker}: {first_line}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
