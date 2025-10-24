from __future__ import annotations
from pathlib import Path
from typing import Tuple
from .settings import settings

WORKSPACE_ROOT = Path(settings.workspace_root).resolve()

def resolve_safe_path(rel_path: str) -> Tuple[Path, bool]:
    target = (WORKSPACE_ROOT / rel_path).resolve()
    try:
        target.relative_to(WORKSPACE_ROOT)
        return target, True
    except Exception:
        return target, False
