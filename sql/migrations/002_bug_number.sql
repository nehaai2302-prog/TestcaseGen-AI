-- Add external bug identifier for search and traceability (e.g. Jira BUG-101).

ALTER TABLE bug_reports
    ADD COLUMN IF NOT EXISTS bug_number TEXT;

CREATE INDEX IF NOT EXISTS idx_bug_reports_project_number
    ON bug_reports(project_id, bug_number);
