-- Per-user project names + fast owner lookups

-- Replace global unique name with per-user uniqueness
DROP INDEX IF EXISTS ux_projects_name_norm;

CREATE UNIQUE INDEX IF NOT EXISTS ux_projects_user_name_norm
    ON projects (user_id, lower(btrim(name)));

CREATE INDEX IF NOT EXISTS idx_projects_user_id
    ON projects (user_id);

CREATE INDEX IF NOT EXISTS idx_projects_user_project
    ON projects (user_id, id);

-- Backfill public.users for any auth users created before the trigger existed
INSERT INTO public.users (id, email)
SELECT id, email
FROM auth.users
ON CONFLICT (id) DO UPDATE SET email = EXCLUDED.email;
