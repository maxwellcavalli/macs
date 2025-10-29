from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pathlib import Path
from typing import Any, Mapping, Optional
import json, asyncio, os, time
from .artifacts import _resolve_root

router = APIRouter()

FINAL_WAIT_SECONDS = float(os.getenv("FINAL_WAIT_SECONDS", "2.0") or "0")
FINAL_WAIT_INTERVAL = max(0.05, float(os.getenv("FINAL_WAIT_INTERVAL", "0.2") or "0.2"))

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

def _load_result_payload(root: Path | None) -> dict[str, Any]:
    if not root or not root.exists() or not root.is_dir():
        return {}
    p = root / "result.json"
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

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

async def _synthesize_payload(task_id: str, request: Request) -> Optional[dict[str, Any]]:
    # 1) Try repository on app.state if present
    try:
        repo = getattr(request.app.state, "task_repo", None)
        if repo and hasattr(repo, "get_by_id"):
            row = await repo.get_by_id(task_id)
            if row:
                payload = _row_to_payload(row, task_id)
                extra = _load_result_payload(_resolve_root(task_id))
                if extra:
                    if extra.get("content"):
                        payload.setdefault("result", extra.get("content"))
                    if extra.get("zip_url"):
                        payload["zip_url"] = extra.get("zip_url")
                    if extra.get("follow_up_steps"):
                        payload["follow_up_steps"] = extra.get("follow_up_steps")
                return payload
    except Exception:
        pass
    # 2) Fallback to artifacts
    root = _resolve_root(task_id)
    text = _read_first_text(root)
    extra = _load_result_payload(root)
    if text or extra or (root and root.exists()):
        payload = {"id": task_id, "status": "done", "result": text, "note": "fallback-artifacts"}
        if extra.get("zip_url"):
            payload["zip_url"] = extra["zip_url"]
        if not payload["result"] and extra.get("content"):
            payload["result"] = extra["content"]
        if extra.get("follow_up_steps"):
            payload["follow_up_steps"] = extra.get("follow_up_steps")
        return payload
    return None

@router.get("/v1/tasks/{task_id}/final")
async def get_task_final(task_id: str, request: Request):
    if FINAL_WAIT_SECONDS <= 0:
        payload = await _synthesize_payload(task_id, request)
        if payload is not None:
            return JSONResponse(payload)
        raise HTTPException(status_code=404, detail="task not found")

    deadline = time.monotonic() + FINAL_WAIT_SECONDS
    while time.monotonic() <= deadline:
        payload = await _synthesize_payload(task_id, request)
        if payload is not None:
            return JSONResponse(payload)
        await asyncio.sleep(FINAL_WAIT_INTERVAL)
    raise HTTPException(status_code=404, detail="task not found")
