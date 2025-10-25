import os
from typing import Any, Dict, List, Tuple

def _row_from_mapping(model: str, v: Dict[str, Any]) -> Dict[str, Any]:
    # file backend typical keys: count, sum, avg, last_ts
    # sometimes alternative keys: n, sum_reward, avg_reward
    return {
        "model_id": model,
        "count": int(v.get("count", v.get("n", 0)) or 0),
        "sum_reward": float(v.get("sum_reward", v.get("sum", 0.0)) or 0.0),
        "avg_reward": float(v.get("avg_reward", v.get("avg", 0.0)) or 0.0),
        "last_ts": v.get("last_ts"),
    }

def _row_from_objectlike(obj: Dict[str, Any]) -> Dict[str, Any]:
    mid = obj.get("model_id", obj.get("model"))
    return {
        "model_id": str(mid) if mid is not None else "unknown",
        "count": int(obj.get("count", obj.get("n", 0)) or 0),
        "sum_reward": float(obj.get("sum_reward", obj.get("sum", 0.0)) or 0.0),
        "avg_reward": float(obj.get("avg_reward", obj.get("avg", 0.0)) or 0.0),
        "last_ts": obj.get("last_ts"),
    }

def choose_backend() -> str:
    """
    Decide backend: explicit BANDIT_BACKEND=pg wins; else DATABASE_URL implies pg; fallback file.
    """
    if os.getenv("BANDIT_BACKEND", "").lower() == "pg":
        return "pg"
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
            backend = "file"
        else:
            data = pg_stats()
            if isinstance(data, dict):
                for model, v in data.items():
                    rows.append(_row_from_mapping(str(model), v or {}))
            elif isinstance(data, list):
                for obj in data:
                    if isinstance(obj, dict):
                        rows.append(_row_from_objectlike(obj))

    if backend == "file":
        try:
            from .bandit_store import get_stats as file_stats
        except Exception:
            return backend, rows
        data = file_stats()
        if isinstance(data, dict):
            for model, v in data.items():
                rows.append(_row_from_mapping(str(model), v or {}))
        elif isinstance(data, list):
            for obj in data:
                if isinstance(obj, dict):
                    rows.append(_row_from_objectlike(obj))

    rows.sort(key=lambda r: (r["last_ts"] or 0, r["count"]), reverse=True)
    return backend, rows

# ---- Unified observations (PG → file fallback) ----

def _normalize_event(ev: Dict[str, Any]) -> Dict[str, Any]:
    ts = ev.get("ts") or ev.get("timestamp") or ev.get("created_at")
    model = ev.get("model_id") or ev.get("model")
    reward = ev.get("reward") if ev.get("reward") is not None else ev.get("r")
    meta = ev.get("meta") if isinstance(ev.get("meta"), dict) else {}
    return {
        "ts": ts,
        "model_id": str(model) if model is not None else "unknown",
        "reward": reward,
        "meta": meta,
    }

def get_observations(limit: int) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Return (backend, events) where each event is:
    { ts, model_id, reward, meta }
    Auto-chooses PG if available; otherwise reads the JSONL file backend.
    """
    if limit < 1:
        limit = 1
    if limit > 500:
        limit = 500

    backend = choose_backend()
    events: List[Dict[str, Any]] = []

    if backend == "pg":
        try:
            from . import bandit_store_pg as pg
            # Try a few likely function names in pg module
            fn = None
            for name in ("get_observations", "observations", "recent", "recent_events", "get_recent_events"):
                cand = getattr(pg, name, None)
                if callable(cand):
                    fn = cand
                    break
            if fn is not None:
                raw = fn(limit)  # expected List[Dict]
                if isinstance(raw, list):
                    for ev in raw:
                        if isinstance(ev, dict):
                            events.append(_normalize_event(ev))
                return "pg", events
            # missing function, fall back to file
            backend = "file"
        except Exception:
            backend = "file"

    if backend == "file":
        try:
            from .bandit_store import get_store_path
        except Exception:
            return "file", events

        from pathlib import Path as _Path
        import json

        path = _Path(get_store_path())
        if not path.exists():
            return "file", events

        try:
            with path.open("rb") as f:
                f.seek(0, 2)
                pos = f.tell()
                buf = b""
                chunk = 4096
                while pos > 0 and len(events) < limit:
                    take = chunk if pos >= chunk else pos
                    pos -= take
                    f.seek(pos)
                    buf = f.read(take) + buf
                    parts = buf.split(b"\n")
                    if pos > 0:
                        buf = parts[0]
                        parts = parts[1:]
                    else:
                        buf = b""
                    for line in reversed(parts):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            ev = json.loads(line.decode("utf-8"))
                            if isinstance(ev, dict):
                                events.append(_normalize_event(ev))
                                if len(events) >= limit:
                                    break
                        except Exception:
                            continue
            events.reverse()
        except Exception:
            # Return whatever we could parse
            pass

        return "file", events

    # If we got here with a different backend string, still return whatever we have
    return backend, events
