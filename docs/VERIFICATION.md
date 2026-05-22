# Verification notes (gold-style checklist)

Use `sample_data/sample_requirements.txt` with imported `sample_bug_reports.csv` and `sample_test_cases.csv`.

## Exhaustiveness levels

| Level | Per requirement | ~10 requirements |
|-------|-----------------|-----------|
| Smoke | 1 positive + 1 negative | ~20 cases |
| Standard | 2 positive + 3 negative + 1 boundary | ~60 cases |
| Exhaustive | 3 positive + 5 negative + 2 boundary + 2 edge | ~120 cases |

After a run, check **Coverage** on the Generate page: requirements fully covered should match requirement count. With default `MAX_COVERAGE_REVIEW_ROUNDS=0`, gaps may remain but the run is faster (no regen loop). Set `MAX_COVERAGE_REVIEW_ROUNDS=1` in `.env` to auto-fill gaps.

The Generate page shows **step-by-step pipeline progress** while the LangGraph runs (`stream_mode="values"`).

## Theme checklist (sample doc)

| # | Requirement theme | Expected in generated tests (manual pass/fail) |
|---|-------------------|---------------------------------------------------|
| 1 | SSO token refresh | Cases mention refresh / re-login / error handling |
| 2 | Double-click pay  | Idempotency / disabled button / duplicate charge prevention |
| 3 | Image 5MB limit   | Boundary / negative file size validation |
| 4 | Search staleness  | Edge case for stale index / banner behavior |

**Traceability:** Each case should have `linked_requirement` (e.g. `FR-2.2` or `REQ-01`), a generated `testcase_id` (e.g. `TC_FR-2.2_NEG_01`), and at least one requirement chunk UUID.

## Scope-aware RAG (demo script)

1. Import `sample_bug_reports.csv` and `sample_test_cases.csv` on **Import**.
2. Ingest + generate on **Generate**.
3. Confirm **Requirements** section shows a **scope** per requirement. The scope can be a UI screen (`Checkout`, `Login`), a service / endpoint (`OrderService`, `POST /api/payments`), a functional area (`AuthN`, `Audit`, `Performance`), or `General` if none apply.
4. Open **Per-requirement RAG queries** — each requirement's query starts with `Scope: <scope>. ...`, except for `General` requirements which omit the prefix and fall back to plain semantic similarity.
5. Confirm **Project history (RAG retrieval)** shows bugs/TCs with similarity scores.
6. Open accepted cases with **history linked** — **Linked project history** lists bug/TC UUIDs, titles, and notes `retrieved for FR-2.2` when the link came from the requirement's scope-aware pool.
7. Export CSV/XLSX from Library and confirm columns match the QA template: `TestCase_ID`, `Requirement_ID`, `Test_Case_Type`, `Test_Scenario`, `Preconditions`, `Test_Steps`, `Expected_Result`.
8. Say aloud: *"We don't filter pgvector by module. We let the scope context drive retrieval: each requirement is embedded as 'Scope: Checkout. Requirement: Coupon code application…' so a payments bug on the same screen surfaces for the coupon-code requirement by semantic proximity. For non-UI requirements (APIs, audit, performance), the same mechanism works with a service or functional-area scope instead of a screen name."*

**E2E checklist:** Create project → import CSVs → ingest TXT → pick exhaustiveness → generate → verify RAG section + coverage matrix → Library search → export CSV/XLSX.
