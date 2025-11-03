-- Purpose: create storage for persistent workspace memories used by the queue
-- Database: PostgreSQL

CREATE TABLE IF NOT EXISTS public.workspace_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES public.tasks(id) ON DELETE CASCADE,
    repo_path TEXT,
    language TEXT,
    mode TEXT,
    status TEXT,
    goal TEXT,
    model TEXT,
    summary TEXT,
    artifact_rel TEXT,
    zip_rel TEXT,
    files JSONB,
    embedding JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.workspace_memories IS 'Historical task outputs and summaries for workspace memory.';
COMMENT ON COLUMN public.workspace_memories.repo_path IS 'Workspace-relative path or identifier for the task input repo.';
COMMENT ON COLUMN public.workspace_memories.files IS 'JSON map of artifact-relative paths to truncated content or hashes.';
COMMENT ON COLUMN public.workspace_memories.embedding IS 'Optional embedding payload stored as JSON (feature-gated).';

CREATE INDEX IF NOT EXISTS idx_workspace_memories_task_id
    ON public.workspace_memories (task_id);

CREATE INDEX IF NOT EXISTS idx_workspace_memories_repo_language
    ON public.workspace_memories (repo_path, language);

CREATE INDEX IF NOT EXISTS idx_workspace_memories_created_at
    ON public.workspace_memories (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_workspace_memories_goal_summary_fts
    ON public.workspace_memories
    USING GIN (to_tsvector('english', coalesce(goal,'') || ' ' || coalesce(summary,'')));
