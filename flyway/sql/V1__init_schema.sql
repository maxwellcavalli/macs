-- V1__init_schema.sql
-- Postgres schema for tasks + streaming events + artifacts
-- Compatible with Flyway (no superuser extensions required).

-- 1) Enums
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'task_type') THEN
    CREATE TYPE task_type AS ENUM ('CODE','PLAN','REFACTOR','TEST','DOC');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'task_status') THEN
    CREATE TYPE task_status AS ENUM ('queued','running','succeeded','failed','cancelled');
  END IF;
END$$;

-- 2) Tables
CREATE TABLE IF NOT EXISTS tasks (
  id          uuid PRIMARY KEY,
  type        varchar(50) NOT NULL,
  status      varchar(50) NOT NULL,
  goal        text,
  language    text,                -- 'python' | 'java' | 'graphql'
  repo        jsonb  NOT NULL DEFAULT '{}'::jsonb,
  constraints jsonb  NOT NULL DEFAULT '{}'::jsonb,
  model       text,
  options     jsonb  NOT NULL DEFAULT '{}'::jsonb,
  metadata    jsonb  NOT NULL DEFAULT '{}'::jsonb,
  result      text,
  error       text,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS task_events (
  id          bigserial PRIMARY KEY,
  task_id     uuid NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  kind        text NOT NULL,                -- e.g., 'delta', 'note', 'complete', 'error'
  data        jsonb NOT NULL DEFAULT '{}'::jsonb,
  delta       text,                         -- token/string delta if applicable
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_task_events_task_time ON task_events(task_id, created_at);

CREATE TABLE IF NOT EXISTS artifacts (
  id          uuid PRIMARY KEY,
  task_id     uuid NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  name        text NOT NULL,
  path        text NOT NULL,
  mime_type   text,
  size_bytes  bigint,
  sha256      text,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_artifacts_task ON artifacts(task_id);

-- 3) Useful indexes
CREATE INDEX IF NOT EXISTS idx_tasks_status_created ON tasks(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_type_created   ON tasks(type,   created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_updated        ON tasks(updated_at DESC);

-- 4) Auto-update updated_at
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_tasks_set_updated_at ON tasks;
CREATE TRIGGER trg_tasks_set_updated_at
BEFORE UPDATE ON tasks
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

