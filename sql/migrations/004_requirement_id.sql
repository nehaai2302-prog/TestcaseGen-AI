-- Preserve source requirement IDs (FR-2.2, US-103, REQ-01, 1.2.3, ...)
-- on requirement chunks so generation can map test cases directly to them.

ALTER TABLE requirements
    ADD COLUMN IF NOT EXISTS requirement_id TEXT;

ALTER TABLE requirements
    ADD COLUMN IF NOT EXISTS is_synthetic_requirement BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_requirements_project_requirement_id
    ON requirements(project_id, requirement_id);

-- The return signature of match_requirements changed (added requirement_id),
-- and Postgres does not allow CREATE OR REPLACE to change RETURNS TABLE columns.
-- Drop first so the new signature can be installed cleanly.
DROP FUNCTION IF EXISTS match_requirements(VECTOR(1536), FLOAT, INT, UUID);

CREATE OR REPLACE FUNCTION match_requirements(
    query_embedding VECTOR(1536),
    match_threshold FLOAT,
    match_count INT,
    p_project_id UUID
)
RETURNS TABLE (
    id UUID,
    requirement_id TEXT,
    document_name TEXT,
    chunk_index INTEGER,
    chunk_text TEXT,
    similarity FLOAT
)
LANGUAGE sql STABLE AS $$
    SELECT r.id, r.requirement_id, r.document_name, r.chunk_index, r.chunk_text,
           (1 - (r.embedding <=> query_embedding))::FLOAT AS similarity
    FROM requirements r
    WHERE r.project_id = p_project_id
      AND r.embedding IS NOT NULL
      AND (1 - (r.embedding <=> query_embedding)) > match_threshold
    ORDER BY r.embedding <=> query_embedding
    LIMIT match_count;
$$;
