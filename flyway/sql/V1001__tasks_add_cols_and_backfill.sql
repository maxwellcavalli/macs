-- V20251025_01__tasks_add_cols_and_backfill.sql
-- Purpose: add missing columns referenced by the API (model_used, latency_ms, template_ver)
--          and optionally backfill latency_ms from timestamps if present.
-- Database: PostgreSQL

-- === Add columns (idempotent) ===
ALTER TABLE public.tasks
    ADD COLUMN IF NOT EXISTS model_used   text,
    ADD COLUMN IF NOT EXISTS latency_ms   integer,
    ADD COLUMN IF NOT EXISTS template_ver integer;

COMMENT ON COLUMN public.tasks.model_used   IS 'Model identifier used to run the task';
COMMENT ON COLUMN public.tasks.latency_ms   IS 'Server-measured latency in milliseconds';
COMMENT ON COLUMN public.tasks.template_ver IS 'Template version used to generate this task';

-- === Optional backfill for latency_ms ===
DO $$
BEGIN
  -- Only proceed if latency_ms and created_at exist
  IF EXISTS (
       SELECT 1 FROM information_schema.columns
       WHERE table_schema='public' AND table_name='tasks' AND column_name='latency_ms'
     )
     AND EXISTS (
       SELECT 1 FROM information_schema.columns
       WHERE table_schema='public' AND table_name='tasks' AND column_name='created_at'
     )
  THEN
    -- Case 1: finished_at exists
    IF EXISTS (
         SELECT 1 FROM information_schema.columns
         WHERE table_schema='public' AND table_name='tasks' AND column_name='finished_at'
       )
    THEN
      UPDATE public.tasks
         SET latency_ms = GREATEST(0, ROUND(EXTRACT(EPOCH FROM (finished_at - created_at)) * 1000))::int
       WHERE latency_ms IS NULL
         AND finished_at IS NOT NULL
         AND created_at  IS NOT NULL;

    -- Case 2: updated_at exists (fallback)
    ELSIF EXISTS (
         SELECT 1 FROM information_schema.columns
         WHERE table_schema='public' AND table_name='tasks' AND column_name='updated_at'
       )
    THEN
      UPDATE public.tasks
         SET latency_ms = GREATEST(0, ROUND(EXTRACT(EPOCH FROM (updated_at - created_at)) * 1000))::int
       WHERE latency_ms IS NULL
         AND updated_at IS NOT NULL
         AND created_at IS NOT NULL;
    END IF;
  END IF;
END
$$;
