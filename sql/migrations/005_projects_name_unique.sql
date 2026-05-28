-- Enforce unique project names (case-insensitive, trimmed)
-- Note: If this fails, clean up existing duplicates first:
-- SELECT lower(btrim(name)) AS normalized_name, count(*)
-- FROM projects
-- GROUP BY lower(btrim(name))
-- HAVING count(*) > 1;

CREATE UNIQUE INDEX IF NOT EXISTS ux_projects_name_norm
    ON projects (lower(btrim(name)));
