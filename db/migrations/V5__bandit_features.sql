-- Add a feature bucket for contextual bandits
ALTER TABLE bandit_observations
  ADD COLUMN IF NOT EXISTS feature_hash TEXT;

-- Helpful indexes
CREATE INDEX IF NOT EXISTS idx_bandit_feature_ts
  ON bandit_observations (feature_hash, ts DESC);

CREATE INDEX IF NOT EXISTS idx_bandit_model_feature_ts
  ON bandit_observations (model_id, feature_hash, ts DESC);
