from __future__ import annotations
import os, yaml, time
from typing import Dict, Any

_DEFAULT = {
    "rule_version": "v1",
    "success_weight": 1.0,
    "latency_penalty_ms": 0.001,
    "human_score_weight": 0.05,
}

_PATH = os.getenv("DUEL_CONFIG_PATH", "./config/duel.yaml")
_CACHE = {"cfg": _DEFAULT.copy(), "mtime": 0.0}

def get_duel_config() -> Dict[str, Any]:
    try:
        st = os.stat(_PATH)
        if st.st_mtime > _CACHE["mtime"]:
            with open(_PATH, "r", encoding="utf-8") as f:
                doc = yaml.safe_load(f) or {}
            cfg = _DEFAULT.copy()
            cfg.update({k:v for k,v in doc.items() if v is not None})
            _CACHE["cfg"] = cfg
            _CACHE["mtime"] = st.st_mtime
    except FileNotFoundError:
        _CACHE["cfg"] = _DEFAULT.copy()
    return _CACHE["cfg"]
