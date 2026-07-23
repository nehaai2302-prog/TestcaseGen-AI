-- Row Level Security: each user sees only their own projects and child rows

ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS users_select_own ON public.users;
CREATE POLICY users_select_own ON public.users
    FOR SELECT
    USING (id = auth.uid());

GRANT SELECT ON public.users TO authenticated;

ALTER TABLE projects ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS projects_select_own ON projects;
CREATE POLICY projects_select_own ON projects
    FOR SELECT
    USING (user_id = auth.uid());

DROP POLICY IF EXISTS projects_insert_own ON projects;
CREATE POLICY projects_insert_own ON projects
    FOR INSERT
    WITH CHECK (user_id = auth.uid());

DROP POLICY IF EXISTS projects_update_own ON projects;
CREATE POLICY projects_update_own ON projects
    FOR UPDATE
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

DROP POLICY IF EXISTS projects_delete_own ON projects;
CREATE POLICY projects_delete_own ON projects
    FOR DELETE
    USING (user_id = auth.uid());

-- Child tables: access via owning project

ALTER TABLE requirements ENABLE ROW LEVEL SECURITY;
ALTER TABLE test_cases ENABLE ROW LEVEL SECURITY;
ALTER TABLE bug_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE generation_history ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS requirements_project_own ON requirements;
CREATE POLICY requirements_project_own ON requirements
    FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM projects p
            WHERE p.id = requirements.project_id AND p.user_id = auth.uid()
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM projects p
            WHERE p.id = requirements.project_id AND p.user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS test_cases_project_own ON test_cases;
CREATE POLICY test_cases_project_own ON test_cases
    FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM projects p
            WHERE p.id = test_cases.project_id AND p.user_id = auth.uid()
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM projects p
            WHERE p.id = test_cases.project_id AND p.user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS bug_reports_project_own ON bug_reports;
CREATE POLICY bug_reports_project_own ON bug_reports
    FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM projects p
            WHERE p.id = bug_reports.project_id AND p.user_id = auth.uid()
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM projects p
            WHERE p.id = bug_reports.project_id AND p.user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS generation_history_project_own ON generation_history;
CREATE POLICY generation_history_project_own ON generation_history
    FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM projects p
            WHERE p.id = generation_history.project_id AND p.user_id = auth.uid()
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM projects p
            WHERE p.id = generation_history.project_id AND p.user_id = auth.uid()
        )
    );
