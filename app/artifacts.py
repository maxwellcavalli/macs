import os, json
from pathlib import Path
from typing import Any, Dict, Optional

_ROOT_CACHE: Optional[Path] = None

_DEFAULT_CANDIDATES = [
    "./artifacts",
    "/data/artifacts",
    "/app/artifacts",
    "/workspace/artifacts",
    "/srv/artifacts",
]

def _select_root() -> Path:
    candidates = []
    env_val = os.getenv("ARTIFACTS_DIR")
    if env_val:
        candidates.append(env_val)
    candidates.extend(_DEFAULT_CANDIDATES)

    for raw in candidates:
        if not raw:
            continue
        try:
            path = Path(raw).expanduser()
        except Exception:
            continue
        try:
            path.mkdir(parents=True, exist_ok=True)
        except Exception:
            continue
        if path.exists() and path.is_dir():
            return path
    fallback = Path("./artifacts")
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback

def _root() -> Path:
    global _ROOT_CACHE
    if _ROOT_CACHE is None:
        _ROOT_CACHE = _select_root()
    return _ROOT_CACHE

def _resolve_root(task_id: str) -> Path:
    base = _root()
    target = base / str(task_id)
    if target.exists():
        return target
    # fallback scan in case artifacts were written to another candidate after cache init
    candidates = []
    env_val = os.getenv("ARTIFACTS_DIR")
    if env_val:
        candidates.append(Path(env_val).expanduser())
    candidates.extend(Path(p).expanduser() for p in _DEFAULT_CANDIDATES)
    for candidate in candidates:
        try:
            if not candidate.exists():
                continue
            alt = candidate / str(task_id)
            if alt.exists():
                # update cache for future lookups
                global _ROOT_CACHE
                _ROOT_CACHE = candidate
                return alt
        except Exception:
            continue
    return target

def write_result(task_id: str, payload: Dict[str, Any]) -> str:
    r = _resolve_root(task_id)
    r.mkdir(parents=True, exist_ok=True)
    (r / "result.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return str(r)
