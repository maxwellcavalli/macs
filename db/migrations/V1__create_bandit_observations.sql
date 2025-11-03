-- Idempotent so it plays nice if the table already exists.
CREATE TABLE IF NOT EXISTS bandit_observations (
  id           BIGSERIAL PRIMARY KEY,
  ts           BIGINT       NOT NULL,
  model_id     TEXT         NOT NULL,
  task_type    TEXT,
  reward       DOUBLE PRECISION NOT NULL,
  won          BOOLEAN      NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bandit_model_ts ON bandit_observations(model_id, ts);
