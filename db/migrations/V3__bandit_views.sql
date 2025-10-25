CREATE OR REPLACE VIEW bandit_model_agg AS
SELECT
  model_id,
  COALESCE(task_type,'*') AS task_type,
  COUNT(*)                                 AS n,
  SUM(CASE WHEN won THEN 1 ELSE 0 END)     AS wins,
  AVG(reward)                               AS avg_reward,
  SUM(reward)                               AS sum_reward,
  MAX(to_timestamp(ts))                     AS last_at
FROM bandit_observations
GROUP BY model_id, COALESCE(task_type,'*');

-- Convenience: top models by sum_reward
CREATE OR REPLACE VIEW bandit_top_models AS
SELECT *
FROM bandit_model_agg
ORDER BY sum_reward DESC, n DESC, model_id ASC;
