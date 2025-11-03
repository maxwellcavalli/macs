ALTER TABLE public.workspace_memories
    ADD COLUMN IF NOT EXISTS session_id UUID;

CREATE INDEX IF NOT EXISTS idx_workspace_memories_mode_session
    ON public.workspace_memories (mode, session_id);
