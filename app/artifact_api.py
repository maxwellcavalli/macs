from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from typing import Any, Mapping
from .artifacts import _resolve_root

router = APIRouter()

def _pick_text(row: Mapping[str, Any]) -> str:
    # look for common text fields
    for k in ("result","output","text","content"):
        v = row.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    msg = row.get("message")
    if isinstance(msg, dict):
        v = msg.get("content")
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""

@router.post("/v1/tasks/{task_id}/ensure_artifact")
async def ensure_artifact(task_id: str, request: Request):
    repo = getattr(request.app.state, "task_repo", None)
    if not repo or not hasattr(repo, "get_by_id"):
        raise HTTPException(503, "task_repo not available")
    row = await repo.get_by_id(task_id)
    if not row:
        raise HTTPException(404, "task not found")
    # mapping/row handling
    data = dict(row) if isinstance(row, Mapping) else dict(getattr(row, "_mapping", {}))
    status = str(data.get("status","")).lower()
    if status not in ("done","error","canceled","running","queued"):
        status = "queued"
    text = _pick_text(data)
    # write artifact (even empty placeholder so early-exit can work)
    root = _resolve_root(task_id)
    root.mkdir(parents=True, exist_ok=True)
    path = root / ("result.md" if text else "result.txt")
    path.write_text(text if text else " ", encoding="utf-8")
    return JSONResponse({"id": task_id, "status": status, "artifact": str(path), "has_text": bool(text)})
