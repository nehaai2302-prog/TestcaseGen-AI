# Manual E2E verification checklist

Use this after Phase 5 implementation. Work through tracks in order when you have time.
For each item, mark **Pass / Fail / Skip** and note what you observed.

Constraint and quality gates marked `[x]` in `PLAN.md` already have pytest coverage.
Focus manual effort on UI flows, auth, RAG, and full generation runs.

**App:** `streamlit run app.py` → usually `http://localhost:8501`

**Related:** `docs/VERIFICATION.md` (sample-data / theme spot-check), `PLAN.md` Verification Checklist

---

## Track 0 — Pre-flight

- [ ] `.env` has `OPENAI_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`**Pass**
- [ ] Migrations `006`–`008` applied in Supabase SQL Editor **Pass**
- [ ] App loads at Home without errors **Pass**

| Result | Notes |
|--------|-------|
| | |

---

## Track 1 — General happy path

**Fixtures:** `sample_data/sample_requirements.txt`, `sample_bug_reports.csv`, `sample_test_cases.csv`

| Step | Action | Pass if | Result |
|------|--------|---------|--------|
| 1 | Home → create a new project | Project appears in picker | |
| 2 | **Import** → upload both CSVs | Import succeeds | |
| 3 | **Generate** → upload `sample_requirements.txt` → **Prepare requirements** | Chunks listed; scopes shown | |
| 4 | Pick **Standard** (faster) or **Exhaustive**; leave **Use project history (RAG)** on | Run starts; pipeline progress shows steps | |
| 5 | After run, check **Coverage** | Fully / Partially / Not covered counts make sense | |
| 6 | Check **Project history (RAG)** | Retrieved / Used / Dropped counts shown | |
| 7 | Open accepted cases → **Linked project history** | Bug/TC links with similarity notes | |
| 8 | **Library** → search + export CSV/XLSX | Columns: `TestCase_ID`, `Requirement_ID`, `Test_Case_Type`, `Test_Scenario`, `Preconditions`, `Test_Steps`, `Expected_Result` | |
| 9 | **Traceability** page | Cases link back to requirement chunks | |

### Theme spot-check (sample doc)

| Theme | Look for in generated cases | Result |
|-------|------------------------------|--------|
| SSO token refresh | refresh / re-login / error handling | |
| Double-click pay | idempotency / disabled button | |
| 5MB image limit | boundary / file size negative | |
| Search staleness | stale index / banner behavior | |

---

## Track 2 — Auth + RLS

Use **two different email accounts** (or incognito for User B).

| Step | Action | Pass if | Result |
|------|--------|---------|--------|
| 1 | **Signup** → new account + project | User + project created | |
| 2 | **Logout** → **Login** | Session restored; project still there | |
| 3 | **Logout** | Session cleared; cannot access project pages without login | |
| 4 | User A creates project; User B logs in | User B does **not** see User A’s project | |
| 5 | (Optional) User B opens User A’s `?project_id=` URL | Access denied / empty / error — not User A’s data | |

---

## Track 3 — RAG isolation

| Step | Action | Pass if | Result |
|------|--------|---------|--------|
| 1 | User A: import bugs/TCs + generate on sample spec | RAG history appears in run | |
| 2 | User B: new project, different spec, generate with RAG on | User A’s bugs/TCs do **not** appear in User B’s retrieval | |

---

## Track 4 — EcoCharge acceptance fixture (Phase 5 core)

Create a **fresh project**. You need the EcoCharge SRS file (referenced in tests as `ecocharge_srs.md`; not committed in the repo).

| Step | Action | Pass if | Result |
|------|--------|---------|--------|
| 1 | Import EcoCharge SRS → **Prepare requirements** | IDs like FR-5, FR-7, FR-8, FR-12, FR-13 appear | |
| 2 | Generate at **Exhaustive** (RAG off is fine if no history) | Run completes | |
| 3 | Check **Specification contradictions** | FR-7/FR-8 (and possibly FR-12/FR-13) flagged | |
| 4 | Check **Open questions for spec author** | Clarifying questions mention boundary/timing conflicts | |
| 5 | Check accepted cases + **Library** | **No** `TC_FR-7_*` or `TC_FR-8_*` persisted | |
| 6 | Check **Cases needing revision** | FR-5 cases without concrete prices land here (coverage may still show quota filled) | |
| 7 | Check **Constraint-rejected cases** | Wrong currency / increment violations caught (e.g. $50, 0.0025) | |
| 8 | Check **Spec-fact rejected cases** | Wrong quiet-hour window rejected; quiet-hours **config** tests pass | |
| 9 | **Export** accepted cases | No contradictory FR-7/FR-8 cases; constraint-valid set only | |

### Known regressions to spot-check

| Check | Pass if | Result |
|-------|---------|--------|
| NFR-3 availability % | Does **not** hit `price_threshold` constraint from FR-9 | |
| FR-10 quiet-hours config | Does **not** appear under Spec-fact rejected | |
| Coupon / length-limit cases | Do **not** land in Cases needing revision for “missing comparison candidate values” | |

---

## Track 5 — Second spec (proves generality)

Use a **non-EcoCharge** SRS — e.g. a small doc with:

1. A **comparison** rule (“pick the lowest-cost 3-hour window from hourly rates”)
2. A **threshold boundary conflict** (strict `<` vs “at or below” on two related rules)

| Step | Action | Pass if | Result |
|------|--------|---------|--------|
| 1 | Upload comparison-only spec → generate | Vague cases without prices → **Cases needing revision** | |
| 2 | Upload contradictory threshold pair → generate | **Specification contradictions** banner; blocked rules skip generation | |
| 3 | Toggle **Use project history (RAG)** off, or use unrelated e-commerce history with EcoCharge-like SRS | Foreign cart/currency cases filtered; **Dropped as off-topic** count > 0 | |

---

## Track 6 — Regen + SRS change

| Step | Action | Pass if | Result |
|------|--------|---------|--------|
| 1 | Leave 1–2 requirements **Not covered** → **Regenerate incomplete requirements** | New accepted cases; old rejections cleared when corrected | |
| 2 | Re-upload same SRS with one requirement changed → **Prepare** | SRS change report shows changed/removed IDs | |
| 3 | Generate again | Old generated cases for changed/removed IDs replaced (not duplicated) | |

---

## Track 7 — Dashboard dedup

| Step | Action | Pass if | Result |
|------|--------|---------|--------|
| 1 | After a run with duplicates, open **Dashboard** | Dedup stats include semantic + verbatim + `removed_cross_req` | |
| 2 | Compare to Generate page **Marked duplicates** | Counts align | |

---

## Automated confidence check (optional)

These are already covered by pytest; run if you want a quick green light before manual UI work:

```powershell
$env:PYTHONPATH="."
pytest tests/test_contradiction_scan.py tests/test_substance.py tests/test_spec_facts.py tests/test_rag_relevance.py tests/test_srs_change.py tests/test_ambiguity.py tests/test_clarifying_questions.py -q
```

### Already covered by automated tests (low manual priority)

- Constraint validation (currency, cross-rule FR-7/FR-9, increment, negative expectations)
- Comparison substance / vague FR-5 rejection
- Contradiction blocking at generate time
- Verbatim + scoped semantic dedup
- Spec-fact extraction logic
- RAG relevance filter logic
- Clarifying questions builder
- SRS change detection

**Skipped for now:** 5.4 Comparison scenario checklist C1–C5

---

## Suggested session order

1. **Track 1** — sample_data happy path (~15 min)
2. **Track 4** — EcoCharge full run (~20–30 min at Exhaustive)
3. **Track 5** — small second spec (~10 min)
4. **Track 6** — regen + SRS change (~10 min)
5. **Track 2** — auth / RLS if multi-user matters for review (~10 min)
6. **Track 3** + **Track 7** — as needed

---

## Session log

| Date | Tracks run | Overall | Notes |
|------|------------|---------|-------|
| | | | |
