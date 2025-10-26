import time
from typing import Any, Dict, List, Optional
from psycopg_pool import ConnectionPool

_DDL = '''
CREATE TABLE IF NOT EXISTS bandit_observations (
  id BIGSERIAL PRIMARY KEY,
  ts BIGINT NOT NULL,
  model_id TEXT NOT NULL,
  task_type TEXT,
  feature_hash TEXT,
  reward DOUBLE PRECISION NOT NULL,
  won BOOLEAN NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bandit_model_ts ON bandit_observations(model_id, ts);
CREATE INDEX IF NOT EXISTS idx_bandit_feature_ts ON bandit_observations(feature_hash, ts DESC);
CREATE INDEX IF NOT EXISTS idx_bandit_model_feature_ts ON bandit_observations(model_id, feature_hash, ts DESC);
'''.strip()

class BanditStorePG:
    def __init__(self, dsn: str, min_size: int = 1, max_size: int = 8) -> None:
        self.pool = ConnectionPool(conninfo=dsn, min_size=min_size, max_size=max_size,
                                   kwargs={"application_name": "macs-bandit-store"})
        self._init_schema()

    def _init_schema(self) -> None:
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute(_DDL)
            # In case table existed from earlier version (no feature_hash)
            cur.execute("ALTER TABLE bandit_observations ADD COLUMN IF NOT EXISTS feature_hash TEXT")
            conn.commit()

    def record(self, model_id: str, reward: float, won: bool,
               task_type: Optional[str] = None, feature_hash: Optional[str] = None) -> None:
        now = int(time.time())
        with self.pool.connection() as conn, conn.cursor() as cur:
            if feature_hash is None:
                cur.execute(
                    "INSERT INTO bandit_observations(ts, model_id, task_type, reward, won) "
                    "VALUES (%s,%s,%s,%s,%s)",
                    (now, model_id, task_type, float(reward), bool(won))
                )
            else:
                cur.execute(
                    "INSERT INTO bandit_observations(ts, model_id, task_type, feature_hash, reward, won) "
                    "VALUES (%s,%s,%s,%s,%s,%s)",
                    (now, model_id, task_type, feature_hash, float(reward), bool(won))
                )
            conn.commit()

    def reset(self, model_id: Optional[str] = None, feature_hash: Optional[str] = None) -> int:
        with self.pool.connection() as conn, conn.cursor() as cur:
            if model_id and feature_hash:
                cur.execute("DELETE FROM bandit_observations WHERE model_id = %s AND feature_hash = %s",
                            (model_id, feature_hash))
            elif model_id:
                cur.execute("DELETE FROM bandit_observations WHERE model_id = %s", (model_id,))
            elif feature_hash:
                cur.execute("DELETE FROM bandit_observations WHERE feature_hash = %s", (feature_hash,))
            else:
                cur.execute("DELETE FROM bandit_observations")
            deleted = cur.rowcount or 0
            conn.commit()
            return deleted

    def stats(self) -> List[Dict[str, Any]]:
        q = '''
        SELECT
          model_id,
          COALESCE(task_type,'*') AS task_type,
          feature_hash,
          COUNT(*)                                 AS n,
          SUM(CASE WHEN won THEN 1 ELSE 0 END)     AS wins,
          ROUND(AVG(reward)::numeric, 6)           AS avg_reward,
          ROUND(SUM(reward)::numeric, 6)           AS sum_reward,
          MAX(ts)                                   AS last_ts
        FROM bandit_observations
        GROUP BY model_id, COALESCE(task_type,'*'), feature_hash
        ORDER BY sum_reward DESC, n DESC, model_id ASC
        '''
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute(q)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
