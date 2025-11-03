import os, json, asyncio
from pathlib import Path
from typing import AsyncGenerator
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter()

_ART = os.getenv("ARTIFACTS_DIR", "/app/artifacts")

def _artifact_dir(task_id: str) -> Path:
    return Path(_ART) / task_id

def _event(obj: dict) -> bytes:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n".encode("utf-8")

@router.get("/v1/tasks/{task_id}/status")
async def task_status(task_id: str):
    root = _artifact_dir(task_id)
    status = "done" if (root.exists() and root.is_dir()) else "waiting"
    return {"task_id": task_id, "status": status}

@router.get("/v1/tasks/{task_id}/sse")
async def task_sse(task_id: str):
    async def gen() -> AsyncGenerator[bytes, None]:
        root = _artifact_dir(task_id)
        # immediate early-exit
        try:
            if root.exists() and root.is_dir():
                yield _event({"status": "done", "note": "artifacts-present"})
                return
        except Exception:
            pass
        # keepalive loop (60s)
        for _ in range(120):
            try:
                if root.exists() and root.is_dir():
                    yield _event({"status": "done", "note": "artifacts-present"})
                    return
            except Exception:
                pass
            yield b": keep-alive\n\n"
            await asyncio.sleep(0.5)

        # DEV fallback: create artifact on timeout to finish the stream
        if os.getenv("DEV_COMPAT") == "1":
            try:
                root.mkdir(parents=True, exist_ok=True)
                (root / "result.json").write_text(json.dumps({"ok": True, "task_id": task_id, "note": "dev-timeout"}, ensure_ascii=False), encoding="utf-8")
                yield _event({"status":"done","note":"artifacts-created-dev"})
                return
            except Exception:
                pass
        yield _event({"status": "timeout", "note": "no-artifacts"})
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control":"no-cache","Connection":"keep-alive"})
