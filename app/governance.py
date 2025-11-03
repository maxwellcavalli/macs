from __future__ import annotations
import json, time, yaml
from typing import Any, Dict
from .settings import settings

with open("./config/policy.yaml","r") as f:
    POLICY = yaml.safe_load(f)

def audit(event: Dict[str, Any]):
    if POLICY.get("logging",{}).get("audit_log") == "enabled":
        line = json.dumps({"ts": time.time(), **event}, ensure_ascii=False)
        with open("./audit.log","a", encoding="utf-8") as fh:
            fh.write(line + "\n")

def enforce_fs_write(path_ok: bool, path: str) -> bool:
    if not path_ok:
        audit({"rule": "FS_OUTSIDE_WORKSPACE", "action": "deny", "path": path})
        return False
    return True
