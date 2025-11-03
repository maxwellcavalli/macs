import os
import zipfile
from pathlib import Path
from typing import Dict

ZIP_ROOT = Path(os.getenv("ZIP_DIR", "/data/zips"))

def _ensure_root() -> Path:
    ZIP_ROOT.mkdir(parents=True, exist_ok=True)
    return ZIP_ROOT

def write_zip(task_id: str, files: Dict[str, str], *, default_name: str = "output.txt") -> Path:
    root = _ensure_root()
    safe_id = task_id.replace("/", "_")
    target = root / f"{safe_id}.zip"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if not files:
            zf.writestr(default_name, "")
        else:
            for name, content in files.items():
                arcname = name or default_name
                zf.writestr(arcname, content or "")
    return target
