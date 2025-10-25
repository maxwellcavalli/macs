import json, os, threading, time
from pathlib import Path
from typing import Any, Dict, Optional

_lock = threading.Lock()

def get_store_path() -> str:
    # Default to the bind-mounted app path
    return os.getenv("BANDIT_STORE_PATH", "/app/data/bandit.jsonl")

def _ensure_parent(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)

def record_event(model: str, reward: float, meta: Optional[Dict[str, Any]] = None, *, path: Optional[str] = None) -> str:
    """
    Append one bandit event as JSONL. Returns the absolute file path used.
    - Resolves path at CALL TIME (not import time), so env changes apply immediately.
    - Flushes and fsyncs to avoid buffering surprises on bind mounts.
    """
    if not model:
        model = "unknown"
    ev = {"ts": time.time(), "model": str(model), "reward": float(reward), "meta": meta or {}}
    target = Path(path or get_store_path())
    _ensure_parent(target)
    line = json.dumps(ev, ensure_ascii=False)
    with _lock:
        with target.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                pass
    return str(target)

def get_stats(*, path: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """
    Aggregate per-model stats: count, sum, avg, last_ts.
    Ignores malformed lines.
    """
    target = Path(path or get_store_path())
    out: Dict[str, Dict[str, Any]] = {}
    if not target.exists():
        return out
    with _lock:
        with target.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except Exception:
                    continue
                model = str(ev.get("model", "unknown"))
                try:
                    reward = float(ev.get("reward", 0.0))
                except Exception:
                    reward = 0.0
                ts = float(ev.get("ts", 0.0))
                s = out.setdefault(model, {"count": 0, "sum": 0.0, "avg": 0.0, "last_ts": 0.0})
                s["count"] += 1
                s["sum"] += reward
                s["avg"] = s["sum"] / s["count"]
                s["last_ts"] = max(s["last_ts"], ts)
    return out
