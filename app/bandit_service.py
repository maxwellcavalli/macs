import os
from typing import Any, Dict, List, Tuple

def _row_from_mapping(model: str, v: Dict[str, Any]) -> Dict[str, Any]:
    # file backend typical keys: count, sum, avg, last_ts
    # sometimes we may see n, sum_reward, avg_reward
    return {
        "model_id": model,
        "count": int(v.get("count", v.get("n", 0)) or 0),
        "sum_reward": float(v.get("sum_reward", v.get("sum", 0.0)) or 0.0),
        "avg_reward": float(v.get("avg_reward", v.get("avg", 0.0)) or 0.0),
        "last_ts": v.get("last_ts"),
    }

def _row_from_objectlike(obj: Dict[str, Any]) -> Dict[str, Any]:
    # pg rows may be dicts like: model/model_id, count/n, sum/sum_reward, avg/avg_reward, last_ts
    mid = obj.get("model_id", obj.get("model"))
    return {
        "model_id": str(mid) if mid is not None else "unknown",
        "count": int(obj.get("count", obj.get("n", 0)) or 0),
        "sum_reward": float(obj.get("sum_reward", obj.get("sum", 0.0)) or 0.0),
        "avg_reward": float(obj.get("avg_reward", obj.get("avg", 0.0)) or 0.0),
        "last_ts": obj.get("last_ts"),
    }

def choose_backend() -> str:
    # Explicit env override
    if os.getenv("BANDIT_BACKEND", "").lower() == "pg":
        return "pg"
    # Auto: prefer PG if DATABASE_URL is set and import works
    if os.getenv("DATABASE_URL"):
        try:
            from . import bandit_store_pg  # noqa: F401
            return "pg"
        except Exception:
            pass
    return "file"

def get_stats_unified() -> Tuple[str, List[Dict[str, Any]]]:
    """
    Returns (backend, rows) with rows in unified schema:
    { model_id, count, sum_reward, avg_reward, last_ts }
    """
    backend = choose_backend()
    rows: List[Dict[str, Any]] = []

    if backend == "pg":
        try:
            from .bandit_store_pg import stats as pg_stats
        except Exception:
            backend = "file"  # graceful fallback
        else:
            data = pg_stats()
            if isinstance(data, dict):
                # map of model -> metrics
                for model, v in data.items():
                    rows.append(_row_from_mapping(str(model), v or {}))
            elif isinstance(data, list):
                # list of rows/dicts
                for obj in data:
                    if isinstance(obj, dict):
                        rows.append(_row_from_objectlike(obj))
            else:
                # unknown shape; leave empty
                pass

    if backend == "file":
        try:
            from .bandit_store import get_stats as file_stats
        except Exception:
            # No fallback; return empty
            return backend, rows
        data = file_stats()
        if isinstance(data, dict):
            for model, v in data.items():
                rows.append(_row_from_mapping(str(model), v or {}))
        elif isinstance(data, list):
            # If file returns array rows (rare), normalize too
            for obj in data:
                if isinstance(obj, dict):
                    rows.append(_row_from_objectlike(obj))

    # Sort: most recent first, then count desc
    rows.sort(key=lambda r: (r["last_ts"] or 0, r["count"]), reverse=True)
    return backend, rows
