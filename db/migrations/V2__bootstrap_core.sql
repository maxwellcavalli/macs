-- Bootstrap core tables to align Flyway with app runtime DDL
-- Safe to run repeatedly (IF NOT EXISTS guards).

CREATE TABLE IF NOT EXISTS tasks (
  id UUID PRIMARY KEY,
  type TEXT NOT NULL,
  language TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  status TEXT NOT NULL,
  latency_ms INT,
  model_used TEXT,
  template_ver TEXT
);

CREATE TABLE IF NOT EXISTS rewards (
  id UUID PRIMARY KEY,
  task_id UUID REFERENCES tasks(id) ON DELETE CASCADE,
  model TEXT NOT NULL,
  success BOOLEAN NOT NULL,
  latency_ms INT,
  human_score INT,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Bandit aggregate stats (per model + feature bucket)
CREATE TABLE IF NOT EXISTS bandit_stats (
  model TEXT NOT NULL,
  feature_hash TEXT NOT NULL,
  runs INT DEFAULT 0,
  reward_sum DOUBLE PRECISION DEFAULT 0,
  reward_sq_sum DOUBLE PRECISION DEFAULT 0,
  last_updated TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (model, feature_hash)
);

-- Helpful indexes (idempotent)
DO $$ BEGIN
  CREATE INDEX IF NOT EXISTS idx_rewards_task ON rewards(task_id);
  CREATE INDEX IF NOT EXISTS idx_rewards_model ON rewards(model);
EXCEPTION WHEN duplicate_table THEN
  -- older Postgres versions may throw on IF NOT EXISTS in CREATE INDEX inside DO blocks; ignore
  NULL;
END $$;
