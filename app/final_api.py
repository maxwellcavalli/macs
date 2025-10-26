from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pathlib import Path
from typing import Any, Mapping
from .artifacts import _resolve_root

router = APIRouter()

def _normalize_status(s: str | None) -> str | None:
    if not s: return s
    s = str(s).strip().lower()
    return {
        "succeeded":"done","success":"done","completed":"done","complete":"done",
        "failed":"error","failure":"error","fail":"error","cancelled":"canceled",
    }.get(s, s)

def _read_first_text(root: Path | None) -> str:
    if not root or not root.exists() or not root.is_dir(): return ""
    for name in ("result.md","output.md","answer.md","result.txt","output.txt","answer.txt"):
        p = root / name
        if p.is_file():
            try:
                s = p.read_text(encoding="utf-8").strip()
                if s: return s
            except Exception: pass
    for p in sorted(root.rglob("*")):
        if p.suffix.lower() in (".md",".txt"):
            try:
                s = p.read_text(encoding="utf-8").strip()
                if s: return s
            except Exception: pass
    return ""

def _row_to_payload(row: Any, task_id: str) -> dict[str, Any]:
    if row is None: return {}
    if isinstance(row, Mapping): d = dict(row)
    else:
        try: d = dict(row._mapping)  # SQLAlchemy Row
        except Exception: d = {k: getattr(row, k) for k in dir(row) if not k.startswith("_")}
    d["id"] = d.get("id", task_id)
    d["status"] = _normalize_status(d.get("status")) or "queued"
    keep = {"id","status","model_used","latency_ms","template_ver","result","output","message","content","note"}
    return {k:v for k,v in d.items() if k in keep}

@router.get("/v1/tasks/{task_id}/final")
async def get_task_final(task_id: str, request: Request):
    # 1) Try repository on app.state if present
    try:
        repo = getattr(request.app.state, "task_repo", None)
        if repo and hasattr(repo, "get_by_id"):
            row = await repo.get_by_id(task_id)
            if row:
                return JSONResponse(_row_to_payload(row, task_id))
    except Exception:
        pass
    # 2) Fallback to artifacts
    root = _resolve_root(task_id)
    text = _read_first_text(root)
    if text or (root and root.exists()):
        return JSONResponse({"id": task_id, "status": "done", "result": text, "note": "fallback-artifacts"})
    raise HTTPException(status_code=404, detail="task not found")
