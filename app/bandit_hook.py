import os, json, time
from typing import Any, Dict, Optional

def _debug(msg: str, **kw: Any) -> None:
    if os.getenv("BANDIT_HOOK_DEBUG"):
        try:
            print(json.dumps({"bandit_hook": msg, **kw, "ts": time.time()}))
        except Exception:
            pass

def log_reward(model: Any, reward: Any, meta: Optional[Dict[str, Any]] = None) -> None:
    """Best-effort: import bandit_store and append an event. Never raise."""
    try:
        m = "unknown" if model in (None, "", False) else str(model)
        try:
            r = float(reward)
        except Exception:
            r = 0.0
        from .bandit_store import record_event
        record_event(m, r, meta or {"src":"queue"})
        _debug("logged", model=m, reward=r)
    except Exception as e:
        _debug("skip_log_error", error=str(e))
