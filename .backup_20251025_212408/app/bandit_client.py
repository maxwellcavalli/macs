from __future__ import annotations
import os, time
from typing import Optional
try:
    from .bandit_store_pg import BanditStorePG
except Exception:
    BanditStorePG = None  # type: ignore

_STORE = None

def _resolve_pg_dsn() -> Optional[str]:
    dsn = os.getenv("BANDIT_PG_DSN")
    if dsn: return dsn
    host = os.getenv("PGHOST") or os.getenv("POSTGRES_HOST")
    user = os.getenv("PGUSER") or os.getenv("POSTGRES_USER")
    pwd  = os.getenv("PGPASSWORD") or os.getenv("POSTGRES_PASSWORD") or ""
    db   = os.getenv("PGDATABASE") or os.getenv("POSTGRES_DB")
    port = os.getenv("PGPORT") or os.getenv("POSTGRES_PORT") or "5432"
    if host and user and db:
        return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"
    return None

def _get_store():
    global _STORE
    if _STORE is not None:
        return _STORE
    if BanditStorePG is None:
        return None
    dsn = _resolve_pg_dsn()
    if not dsn:
        return None
    try:
        pool_min = int(os.getenv("BANDIT_POOL_MIN", "1"))
        pool_max = int(os.getenv("BANDIT_POOL_MAX", "8"))
        _STORE = BanditStorePG(dsn, min_size=pool_min, max_size=pool_max)
        return _STORE
    except Exception:
        return None

def record(model_id: str, reward: float, won: bool, task_type: Optional[str] = None) -> None:
    """
    Fire-and-forget: attempts to persist, no-ops if store/env not ready.
    """
    try:
        st = _get_store()
        if st is None: 
            return
        st.record(model_id, reward, won, task_type)
    except Exception:
        # swallow errors to never break main flow
        return
