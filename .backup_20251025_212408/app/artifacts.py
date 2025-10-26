import os, json
from pathlib import Path
from typing import Any, Dict, Optional

def _root() -> Path:
    base = os.getenv("ARTIFACTS_DIR", "/app/artifacts")
    p = Path(base)
    p.mkdir(parents=True, exist_ok=True)
    return p

def _resolve_root(task_id: str) -> Path:
    return _root() / str(task_id)

def write_result(task_id: str, payload: Dict[str, Any]) -> str:
    r = _resolve_root(task_id)
    r.mkdir(parents=True, exist_ok=True)
    (r / "result.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return str(r)
