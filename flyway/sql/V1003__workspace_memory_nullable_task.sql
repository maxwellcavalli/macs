-- Allow workspace memories without a backing task (bootstrap ingest)
ALTER TABLE public.workspace_memories
    DROP CONSTRAINT IF EXISTS workspace_memories_task_id_fkey;

ALTER TABLE public.workspace_memories
    ALTER COLUMN task_id DROP NOT NULL;

ALTER TABLE public.workspace_memories
    ADD CONSTRAINT workspace_memories_task_id_fkey
    FOREIGN KEY (task_id)
    REFERENCES public.tasks(id)
    ON DELETE SET NULL;
