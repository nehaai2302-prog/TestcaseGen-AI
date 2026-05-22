-- TestCraft AI: initial schema for Supabase (PostgreSQL + pgvector)
-- Run in Supabase SQL Editor or via migration tooling.
-- Embedding dimension must match OpenAI text-embedding-3-small default: 1536

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS projects (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS requirements (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_name TEXT NOT NULL,
    requirement_id TEXT,
    is_synthetic_requirement BOOLEAN NOT NULL DEFAULT FALSE,
    chunk_text TEXT NOT NULL,
    chunk_index INTEGER NOT NULL DEFAULT 0,
    module TEXT,
    content_hash TEXT,
    embedding VECTOR(1536),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (project_id, document_name, chunk_index)
);

CREATE TABLE IF NOT EXISTS test_cases (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    testcase_id TEXT,
    title TEXT NOT NULL,
    description TEXT,
    preconditions TEXT,
    steps JSONB NOT NULL DEFAULT '[]'::jsonb,
    expected_result TEXT,
    test_type TEXT NOT NULL,
    priority TEXT NOT NULL DEFAULT 'medium',
    module TEXT,
    linked_requirement TEXT,
    source TEXT NOT NULL DEFAULT 'generated',
    is_duplicate BOOLEAN NOT NULL DEFAULT FALSE,
    similar_to_title TEXT,
    source_requirement_chunk_ids UUID[] DEFAULT ARRAY[]::UUID[],
    supporting_bug_ids UUID[] DEFAULT ARRAY[]::UUID[],
    supporting_test_case_ids UUID[] DEFAULT ARRAY[]::UUID[],
    embedding VECTOR(1536),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_test_cases_project ON test_cases(project_id);
CREATE INDEX IF NOT EXISTS idx_test_cases_project_testcase_id
    ON test_cases(project_id, testcase_id);
CREATE INDEX IF NOT EXISTS idx_requirements_project ON requirements(project_id);
CREATE INDEX IF NOT EXISTS idx_requirements_project_requirement_id
    ON requirements(project_id, requirement_id);

CREATE TABLE IF NOT EXISTS bug_reports (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    bug_number TEXT,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    severity TEXT,
    component TEXT,
    resolution TEXT,
    embedding VECTOR(1536),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bug_reports_project ON bug_reports(project_id);
CREATE INDEX IF NOT EXISTS idx_bug_reports_project_number
    ON bug_reports(project_id, bug_number);

CREATE TABLE IF NOT EXISTS generation_history (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    requirement_doc TEXT,
    test_cases_generated INTEGER NOT NULL DEFAULT 0,
    duplicates_found INTEGER NOT NULL DEFAULT 0,
    agent_looped_back BOOLEAN NOT NULL DEFAULT FALSE,
    model_name TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Vector similarity search helpers (cosine distance <=>; vectors should be normalized for OpenAI embeddings)

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

CREATE OR REPLACE FUNCTION match_test_cases(
    query_embedding VECTOR(1536),
    match_threshold FLOAT,
    match_count INT,
    p_project_id UUID
)
RETURNS TABLE (
    id UUID,
    title TEXT,
    description TEXT,
    test_type TEXT,
    similarity FLOAT
)
LANGUAGE sql STABLE AS $$
    SELECT tc.id, tc.title, tc.description, tc.test_type,
           (1 - (tc.embedding <=> query_embedding))::FLOAT AS similarity
    FROM test_cases tc
    WHERE tc.project_id = p_project_id
      AND tc.embedding IS NOT NULL
      AND (1 - (tc.embedding <=> query_embedding)) > match_threshold
    ORDER BY tc.embedding <=> query_embedding
    LIMIT match_count;
$$;

CREATE OR REPLACE FUNCTION match_bug_reports(
    query_embedding VECTOR(1536),
    match_threshold FLOAT,
    match_count INT,
    p_project_id UUID
)
RETURNS TABLE (
    id UUID,
    title TEXT,
    description TEXT,
    severity TEXT,
    similarity FLOAT
)
LANGUAGE sql STABLE AS $$
    SELECT b.id, b.title, b.description, b.severity,
           (1 - (b.embedding <=> query_embedding))::FLOAT AS similarity
    FROM bug_reports b
    WHERE b.project_id = p_project_id
      AND b.embedding IS NOT NULL
      AND (1 - (b.embedding <=> query_embedding)) > match_threshold
    ORDER BY b.embedding <=> query_embedding
    LIMIT match_count;
$$;

COMMENT ON TABLE requirements IS 'Chunked requirement text with embeddings for RAG';
COMMENT ON TABLE test_cases IS 'Imported or generated test cases with optional embeddings for semantic search and dedup';
