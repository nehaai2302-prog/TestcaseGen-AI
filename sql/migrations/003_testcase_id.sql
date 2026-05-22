-- External / tool test case identifier (e.g. TestRail ID, spreadsheet TestCase_ID).

ALTER TABLE test_cases
    ADD COLUMN IF NOT EXISTS testcase_id TEXT;

CREATE INDEX IF NOT EXISTS idx_test_cases_project_testcase_id
    ON test_cases(project_id, testcase_id);
