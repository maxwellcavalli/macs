from __future__ import annotations
import os, time, threading
from typing import Dict, Tuple

RL_RPS   = float(os.getenv("RL_RPS", "3"))
RL_BURST = int(os.getenv("RL_BURST", "6"))

_state: Dict[str, Tuple[float, float]] = {}
_lock = threading.Lock()

def _now() -> float: return time.monotonic()

def check_allow(key: str) -> Tuple[bool, int]:
    if RL_RPS <= 0: return True, 0
    now = _now()
    with _lock:
        tokens, last = _state.get(key, (float(RL_BURST), now))
        tokens = min(float(RL_BURST), tokens + (now - last) * RL_RPS)
        if tokens >= 1.0:
            tokens -= 1.0
            _state[key] = (tokens, now)
            return True, 0
        need = 1.0 - tokens
        wait_s = need / RL_RPS if RL_RPS > 0 else 1.0
        retry_ms = max(1, int(wait_s * 1000))
        _state[key] = (tokens, now)
        return False, retry_ms

def peek_state(key: str) -> Tuple[float, float, float, int]:
    """Non-mutating read of current tokens, last_ts, and config."""
    now = _now()
    with _lock:
        tokens, last = _state.get(key, (float(RL_BURST), now))
        # what tokens would be *if* we refilled now (without saving)
        tokens = min(float(RL_BURST), tokens + (now - last) * RL_RPS)
        return tokens, last, RL_RPS, RL_BURST
