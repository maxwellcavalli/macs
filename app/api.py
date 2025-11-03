from __future__ import annotations

import asyncio
import html
import io
import json
import os
import time
import uuid
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
from .schemas import (
    TaskV11,
    TaskStatus,
    FeedbackV1,
    WorkspaceMemory,
    WorkspaceMemorySearchResponse,
)
from .settings import settings
from .sse import StreamHub
from .db import get_engine, insert_task, update_task_status, get_task
from sqlalchemy import text
from .registry import available_models
from .bandit import extract_features, feature_hash, get_stats_for_models, estimate_mean
from .ollama_health import get_ollama_health
from .ratelimit import check_allow, peek_state
from .logging_setup import get_logger
from .metrics import sse_terminated_total
from .memory import search_memories, get_memory, record_upload_bundle
from .fs_sandbox import resolve_safe_path
from .java_utils import fix_java_package, fix_java_filename
from .final_api import _synthesize_payload
from .workspace_io import stage_upload

router = APIRouter()
logger = get_logger(__name__)
log = get_logger("api")
hub: StreamHub = StreamHub()
job_queue = None  # set in main

ZIP_ROOT = Path(os.getenv("ZIP_DIR", "/data/zips"))

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_UPLOAD_FILES = 200
MAX_UPLOAD_CONTENT_BYTES = 20 * 1024 * 1024
MAX_UPLOAD_MEMORY_FILES = 10
MAX_UPLOAD_SNIPPET_BYTES = 1024
SUMMARY_LIMIT_BYTES = 4096
MEMORY_UPLOAD_EXTRACT = (os.getenv("MEMORY_UPLOAD_EXTRACT", "1") or "1").lower() not in {"0","false","no"}


def _ratelimit_guard(x_api_key: str|None):
    key = x_api_key or "anon"
    ok, retry_ms = check_allow(key)
    if not ok:
        raise HTTPException(status_code=429, detail=f"rate limit exceeded; retry in {retry_ms}ms", headers={"Retry-After": str(max(1, int((retry_ms+999)//1000)))})


def require_api_key(x_api_key: Optional[str] = Header(None)):
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

@router.get("/health")
async def health():
    return {"ok": True}

@router.get("/v1/ollama/health")
async def ollama_health():
    return await get_ollama_health()

@router.get("/v1/ratelimit/check")
async def ratelimit_check(x_api_key: str | None = Header(None), consume: int = 0):
    key = x_api_key or "anon"
    if consume:
        from .ratelimit import check_allow
        ok, retry_ms = check_allow(key)
        status = "allowed" if ok else f"blocked (retry_in_ms={retry_ms})"
    else:
        status = "peek"
    tokens, last, rps, burst = peek_state(key)
    return {"key": key, "mode": status, "tokens": round(tokens, 3), "rps": rps, "burst": burst}

@router.get("/v1/models")
async def list_models(language: Optional[str] = None, debug: int = Query(0, ge=0, le=1)):
    models = available_models(language)
    if not debug:
        return {"models": models}
    # attach bandit mean estimates for a default feature context (based on provided language)
    dummy_job = {
        "input": {
            "language": language or "any",
            "frameworks": [],
            "repo": {"path": "./workspace", "include": [], "exclude": []},
            "constraints": {"max_tokens": 2048},
            "goal": ""
        },
        "output_contract": {"expected_files": []}
    }
    feats = extract_features(dummy_job)
    fh = feature_hash(feats)
    full_names = [f"{m.get('name')}:{(m.get('size') if str(m.get('size','')).endswith('b') else (str(m.get('size',''))+'b' if m.get('size') else ''))}-{m.get('quant','')}".strip("-") for m in models]
    eng = await get_engine()
    async with eng.connect() as conn:
        stats = await get_stats_for_models(conn, full_names, fh)
    enriched = []
    for m, name in zip(models, full_names):
        runs, rs = stats.get(name, (0, 0.0))
        enriched.append({**m, "_bandit":{"runs":runs, "mean_estimate": round(estimate_mean(runs, rs), 3)}})
    return {"models": enriched, "_feature_hash": fh, "_features": feats}

@router.post("/v1/tasks", dependencies=[Depends(require_api_key)])
async def submit_task(task: TaskV11, request: Request, x_api_key: str | None = Header(None)):
    eng = await get_engine()
    async with eng.begin() as conn:
        await insert_task(conn, task.id, task.type, task.input.language, "queued", task.prompt_template_version)
    # robust queue lookup: module global or app.state
    q = job_queue or getattr(request.app.state, 'job_queue', None)
    if q is None:
        raise HTTPException(status_code=503, detail='job queue not ready')
    payload = task.model_dump()
    metadata = payload.get("metadata") or {}
    ctx_ids = metadata.get("memory_context_ids") or []
    if ctx_ids:
        snippets = []
        for mem_id in ctx_ids:
            try:
                record = await get_memory(str(mem_id))
            except Exception:
                record = None
            if not record:
                continue
            summary = (record.get("summary") or "")[:800]
            snippets.append({
                "id": str(record.get("id")),
                "goal": record.get("goal"),
                "summary": summary,
                "model": record.get("model"),
                "created_at": record.get("created_at"),
                "files": record.get("files") or {},
            })
        if snippets:
            metadata["memory_context"] = snippets
            log.info(
                "task.memory_context.attached",
                {
                    "task_id": str(task.id),
                    "memory_ids": [s.get("id") for s in snippets],
                },
            )
        else:
            log.info(
                "task.memory_context.missing",
                {
                    "task_id": str(task.id),
                    "requested_ids": ctx_ids,
                },
            )
            metadata.pop("memory_context_ids", None)
    payload["metadata"] = metadata
    await q.submit(payload)
    return {"task_id": str(task.id)}

@router.get("/v1/tasks/{task_id}")
async def get_task_status(task_id: uuid.UUID) -> TaskStatus:
    eng = await get_engine()
    async with eng.connect() as conn:
        row = await get_task(conn, task_id)
        if not row:
            raise HTTPException(404, "task not found")
        return TaskStatus(id=task_id, status=row.status, model_used=row.model_used, latency_ms=row.latency_ms, template_ver=row.template_ver)

@router.post("/v1/tasks/{task_id}/cancel", dependencies=[Depends(require_api_key)])
async def cancel_task(task_id: uuid.UUID, request: Request, x_api_key: str | None = Header(None)):
    _ratelimit_guard(x_api_key)
    eng = await get_engine()
    async with eng.begin() as conn:
        await update_task_status(conn, task_id, "canceled")
    # cancel inflight work as well
    q = getattr(request.app.state, 'job_queue', None)
    if q is not None:
        await q.cancel(str(task_id))
    await hub.publish(str(task_id), json.dumps({"status":"canceled"}))
    return {"ok": True}

@router.post("/v1/feedback", dependencies=[Depends(require_api_key)])
async def submit_feedback(feedback: FeedbackV1, x_api_key: str | None = Header(None)):
    _ratelimit_guard(x_api_key)
    eng = await get_engine()
    async with eng.begin() as conn:
        await conn.execute(text("""
            INSERT INTO rewards(id, task_id, model, success, latency_ms, human_score)
            VALUES (gen_random_uuid(), :task_id, :model, :success, :latency_ms, :human_score)
        """), dict(task_id=str(feedback.task_id), model=feedback.model, success=feedback.success,
                   latency_ms=feedback.latency_ms, human_score=feedback.human_score))
        bonus = (feedback.human_score or 0) * 0.02
        await conn.execute(text("""
            INSERT INTO bandit_stats(model, feature_hash, runs, reward_sum, reward_sq_sum, last_updated)
            VALUES (:model, :fh, 1, :r, :r2, now())
            ON CONFLICT (model, feature_hash)
            DO UPDATE SET
                runs = bandit_stats.runs + 1,
                reward_sum = bandit_stats.reward_sum + EXCLUDED.reward_sum,
                reward_sq_sum = bandit_stats.reward_sq_sum + EXCLUDED.reward_sq_sum,
                last_updated = now()
        """), dict(model=feedback.model, fh="manual", r=(1.0 if feedback.success else 0.0)+bonus, r2=((1.0 if feedback.success else 0.0)+bonus)**2))
    return {"ok": True}


@router.get(
    "/v1/memory/search",
    response_model=WorkspaceMemorySearchResponse,
    dependencies=[Depends(require_api_key)],
)
async def workspace_memory_search(
    repo: Optional[str] = Query(None),
    language: Optional[str] = Query(None),
    query: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
    limit: int = Query(5, ge=1, le=25),
):
    if not settings.workspace_memory_enabled:
        return WorkspaceMemorySearchResponse(memories=[])
    records = await search_memories(
        repo_path=repo,
        language=language,
        query=query,
        session_id=session_id,
        limit=limit,
    )
    return WorkspaceMemorySearchResponse(
        memories=[WorkspaceMemory(**row) for row in records]
    )


@router.get(
    "/v1/memory/{memory_id}",
    response_model=WorkspaceMemory,
    dependencies=[Depends(require_api_key)],
)
async def workspace_memory_detail(memory_id: uuid.UUID):
    if not settings.workspace_memory_enabled:
        raise HTTPException(status_code=404, detail="workspace memory disabled")
    record = await get_memory(str(memory_id))
    if not record:
        raise HTTPException(status_code=404, detail="memory not found")
    return WorkspaceMemory(**record)


@router.post(
    "/v1/memory/upload",
    dependencies=[Depends(require_api_key)],
)
async def workspace_memory_upload(
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
    repo_path: Optional[str] = Form(None),
):
    if not settings.workspace_memory_enabled:
        raise HTTPException(status_code=503, detail="workspace memory disabled")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty upload")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="upload too large (max 10MB)")

    try:
        session_uuid = str(uuid.UUID(session_id)) if session_id else str(uuid.uuid4())
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid session_id")

    def _clean_relative(value: Optional[str]) -> str:
        if not value:
            return ""
        value = str(value).strip().replace("\\", "/")
        while value.startswith("./"):
            value = value[2:]
        value = value.strip("/")
        parts = [part for part in value.split("/") if part and part not in {".", ".."}]
        return "/".join(parts)

    repo_label_input = _clean_relative(repo_path)

    try:
        zip_file = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="upload must be a zip archive")

    # Remove prior upload memories for this session (and legacy rows without session_id)
    try:
        engine = await get_engine()
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    DELETE FROM public.workspace_memories
                    WHERE mode = 'upload' AND (session_id = :sid OR (session_id IS NULL AND model = 'memory-upload'))
                    """
                ),
                {"sid": session_uuid},
            )
    except Exception:
        pass

    texts: list[tuple[str, str, bytes]] = []
    try:
        members = [zi for zi in zip_file.infolist() if not zi.is_dir()]
        if len(members) > MAX_UPLOAD_FILES:
            raise HTTPException(status_code=400, detail="too many files in archive (limit 200)")
        total_uncompressed = sum(zi.file_size for zi in members)
        if total_uncompressed > MAX_UPLOAD_CONTENT_BYTES:
            raise HTTPException(status_code=400, detail="archive content too large (limit 20MB)")
        for info in members:
            if info.file_size > MAX_UPLOAD_BYTES:
                continue
            name = info.filename
            if not name or name.endswith("/"):
                continue
            path_obj = Path(name)
            if any(part in {"..", ""} for part in path_obj.parts):
                continue
            try:
                content_bytes = zip_file.read(info)
            except Exception:
                continue
            if len(content_bytes) > MAX_UPLOAD_BYTES:
                content_bytes = content_bytes[:MAX_UPLOAD_BYTES]
            try:
                text = content_bytes.decode("utf-8")
            except UnicodeDecodeError:
                try:
                    text = content_bytes.decode("latin-1")
                except Exception:
                    continue
            texts.append((path_obj.as_posix(), text, content_bytes))
    finally:
        zip_file.close()

    if not texts:
        raise HTTPException(status_code=400, detail="archive contained no usable text files")

    raw_entries: List[tuple[str, str, bytes]] = []
    for rel_path, content, content_bytes in texts:
        raw_entries.append((rel_path, content, content_bytes))

    root_candidates = {
        Path(rel_path).parts[0]
        for rel_path, _, _ in raw_entries
        if Path(rel_path).parts
    }
    flatten_root = None
    if not repo_label_input and len(root_candidates) == 1:
        flatten_root = next(iter(root_candidates))

    def _adjust_rel(rel: str) -> Optional[str]:
        parts = list(Path(rel).parts)
        if not parts:
            return None
        if flatten_root and parts[0] == flatten_root:
            parts = parts[1:]
        adjusted = "/".join(parts)
        return adjusted or None

    trimmed_files: List[tuple[str, str]] = []
    adjusted_entries: List[tuple[str, bytes]] = []
    for rel_path, content, content_bytes in raw_entries:
        adjusted_rel = _adjust_rel(rel_path) or rel_path
        snippet = content[:MAX_UPLOAD_SNIPPET_BYTES]
        trimmed_files.append((adjusted_rel, snippet))
        adjusted_entries.append((adjusted_rel, content_bytes))

    files_payload: Dict[str, Any] = {"files": {}}
    for rel_path, snippet in trimmed_files[:MAX_UPLOAD_MEMORY_FILES]:
        files_payload["files"][rel_path] = snippet
    if trimmed_files:
        files_payload["artifact"] = trimmed_files[0][0]

    def build_summary(entries: List[tuple[str, str]]) -> str:
        parts: List[str] = []
        total = 0
        for rel, snippet in entries:
            chunk = f"File: {rel}\n{snippet}\n"
            parts.append(chunk)
            total += len(chunk)
            if total >= SUMMARY_LIMIT_BYTES:
                break
        summary_text = "".join(parts)
        if len(summary_text) > SUMMARY_LIMIT_BYTES:
            summary_text = summary_text[: SUMMARY_LIMIT_BYTES - 3] + "..."
        return summary_text

    summary_text = build_summary(trimmed_files)
    goal_text = f"Uploaded archive ({file.filename or 'upload.zip'})"

    repo_rel_base, extracted_files, workspace_path = stage_upload(session_uuid, repo_label_input, adjusted_entries)

    row = await record_upload_bundle(
        session_id=session_uuid,
        repo_path=repo_rel_base,
        goal=goal_text,
        summary=summary_text,
        files_payload=files_payload,
        model="memory-upload",
    )

    if not row:
        raise HTTPException(status_code=400, detail="no files ingested")

    return {
        "session_id": session_uuid,
        "repo_path": repo_rel_base,
        "memories": [
            {
                "id": str(row.get("id")),
                "goal": row.get("goal"),
                "summary": row.get("summary"),
                "model": row.get("model"),
                "language": row.get("language"),
                "created_at": row.get("created_at"),
            }
        ],
        "extracted_files": extracted_files,
        "workspace_path": workspace_path,
    }


@router.get("/v1/stream/{task_id}")
async def stream_task(task_id: uuid.UUID, request: Request):
    async def event_gen():

        last_check = 0.0
        last_db_check = 0.0
        db_poll_interval = max(0.5, float(os.getenv("SSE_DB_POLL_INTERVAL", "2.0") or "2.0"))
        final_wait_max = max(1.0, float(os.getenv("SSE_FINAL_WAIT_SECONDS", "20.0") or "20.0"))
        final_retry_interval = max(0.05, float(os.getenv("SSE_FINAL_RETRY_INTERVAL", "0.2") or "0.2"))

        async def fetch_final_payload() -> Optional[dict]:
            try:
                payload = await _synthesize_payload(str(task_id), request)
                if payload:
                    payload.setdefault("status", "done")
                    payload["pending_final"] = False
                return payload
            except Exception:
                return None

        async def wait_for_final_payload() -> Optional[dict]:
            deadline = time.time() + final_wait_max
            while True:
                payload = await fetch_final_payload()
                if payload is not None:
                    return payload
                if time.time() >= deadline:
                    return None
                await asyncio.sleep(final_retry_interval)

        def rebuild_chunk(original: str, data: dict, event_override: Optional[str] = None) -> str:
            event_name = event_override
            if event_name is None:
                for line in original.splitlines():
                    if line.startswith("event: "):
                        event_name = line[7:].strip()
                        break
            payload_text = json.dumps(data)
            if event_name:
                return f"event: {event_name}\ndata: {payload_text}\n\n"
            return f"data: {payload_text}\n\n"

        async for chunk in hub.stream(str(task_id), heartbeat_seconds=10):
            parsed_payload = None
            event_name = None
            if chunk.startswith("data: "):
                raw = chunk[6:].strip()
                try:
                    parsed_payload = json.loads(raw)
                except Exception:
                    parsed_payload = None
            elif chunk.startswith("event: "):
                lines = chunk.splitlines()
                for line in lines:
                    if line.startswith("event: "):
                        event_name = line[7:].strip()
                    if line.startswith("data: "):
                        raw = line[6:].strip()
                        try:
                            parsed_payload = json.loads(raw)
                        except Exception:
                            parsed_payload = None
                        break
            chunk_to_send = chunk

            # forward chunk to client
            if parsed_payload and parsed_payload.get("status") == "done":
                # Merge final payload to ensure readiness
                final_payload = await wait_for_final_payload()
                if final_payload is None:
                    await asyncio.sleep(final_retry_interval)
                    continue
                merge_keys = (
                    "model", "latency_ms", "compile_pass", "test_pass", "tool",
                    "artifact", "logs", "content", "zip_url", "zip_notes", "follow_up_steps"
                )
                for key in merge_keys:
                    value = parsed_payload.get(key)
                    if value not in (None, "") and key not in final_payload:
                        final_payload[key] = value
                final_payload.setdefault("pending_final", False)
                chunk_to_send = rebuild_chunk(chunk, final_payload, event_name)
                parsed_payload = final_payload

            yield chunk_to_send

            if parsed_payload and parsed_payload.get("status") == "done":
                if parsed_payload.get("pending_final"):
                    continue
                try:
                    hub.close(str(task_id))
                except Exception:
                    pass
                try:
                    sse_terminated_total.labels(reason="status").inc()
                except Exception:
                    pass
                logger.info("sse_close", extra={"reason":"status","task_id":str(task_id)})
                break
            if parsed_payload and parsed_payload.get("status") in {"error", "canceled"}:
                try:
                    hub.close(str(task_id))
                except Exception:
                    pass
                try:
                    sse_terminated_total.labels(reason="status").inc()
                except Exception:
                    pass
                logger.info("sse_close", extra={"reason":"status","task_id":str(task_id)})
                break
            # Periodically check for artifacts as a completion signal
            now = time.time()
            if now - last_check >= 2.0:
                last_check = now
                try:
                    payload = await fetch_final_payload()
                    if payload:
                        chunk_payload = rebuild_chunk("event: done\n", payload, "done")
                        yield chunk_payload
                        try:
                            hub.close(str(task_id))
                        except Exception:
                            pass
                        try:
                            sse_terminated_total.labels(reason="artifacts").inc()
                        except Exception:
                            pass
                        logger.info("sse_close", extra={"reason":"artifacts","task_id":str(task_id)})
                        break
                except Exception:
                    # artifacts module not available or other error; ignore
                    pass
            # Poll DB for terminal status as a reliable fallback
            if now - last_db_check >= db_poll_interval:
                last_db_check = now
                eng = await get_engine()
                async with eng.begin() as conn:
                    row = await get_task(conn, task_id)
                status = (row[1] if row else None)
                if status in ("done", "error", "canceled"):
                    if status == "done":
                        payload = await wait_for_final_payload()
                        if payload is None:
                            await asyncio.sleep(final_retry_interval)
                            continue
                        chunk_payload = rebuild_chunk("event: done\n", payload, "done")
                    else:
                        payload = {"status": status, "note": "db-poll", "pending_final": False}
                        chunk_payload = rebuild_chunk("event: done\n", payload, "done")
                    yield chunk_payload
                    try:
                        hub.close(str(task_id))
                    except Exception:
                        pass
                    try:
                        sse_terminated_total.labels(reason="db").inc()
                    except Exception:
                        pass
                    logger.info("sse_close", extra={"reason":"db","task_id":str(task_id)})
                    break
        
    return StreamingResponse(event_gen(), media_type="text/event-stream")

@router.get("/zips/{filename}")
async def download_zip(filename: str):
    file_path = ZIP_ROOT / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="zip not found")
    return FileResponse(file_path, media_type="application/zip", filename=filename)

@router.get("/v1/tasks/{task_id}/zip")
async def download_task_zip(task_id: uuid.UUID):
    filename = f"{task_id}.zip"
    file_path = ZIP_ROOT / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="zip not found")
    return FileResponse(file_path, media_type="application/zip", filename=filename)

# --- dev helper: audit tail ---
@router.get("/v1/audit")
async def audit_tail(n: int = Query(default=100, ge=1, le=1000)):
    """
    Return last N lines from audit.log (NDJSON strings).
    """
    path = "./audit.log"
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()[-n:]
        return JSONResponse(content={"lines": [ln.rstrip("\n") for ln in lines]})
    except FileNotFoundError:
        return JSONResponse(content={"lines": []})

# --- Prometheus metrics endpoint ---
@router.get("/metrics")
async def metrics_endpoint():
    import os
    if os.getenv("METRICS_PUBLIC","0") != "1":
        from fastapi import Request, HTTPException
        raise HTTPException(status_code=403, detail="metrics disabled")
    # Local imports so we don't have to edit global import lines
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    from starlette.responses import Response as StarletteResponse
# --- Bandit API ---
try:
    from fastapi import APIRouter, HTTPException
    _bandit_router = APIRouter()

    @_bandit_router.post("/v1/bandit/record")
    async def bandit_record(payload: dict):
        try:
            from .bandit_store import record_event as _bandit_record_event
        except Exception:
            raise HTTPException(status_code=503, detail="bandit_store unavailable")
        # accept both shapes
        model = str(payload.get("model") or payload.get("model_id") or "unknown")
        try:
            reward = float(payload.get("reward"))
        except Exception:
            raise HTTPException(status_code=422, detail="reward must be a number")
        meta = payload.get("meta") or {}
        # keep model_id in meta when provided (helps downstream normalization)
        if payload.get("model_id") and not payload.get("model"):
            meta["model_id"] = str(payload["model_id"])
        _bandit_record_event(model, reward, meta)
        return {"ok": True, "resolved_model": model}

    @_bandit_router.get("/v1/bandit/stats")
    async def bandit_stats():
        try:
            from .bandit_store import get_stats as _bandit_get_stats
        except Exception:
            raise HTTPException(status_code=503, detail="bandit_store unavailable")
        return {"ok": True, "backend": "file", "stats": _bandit_get_stats()}

    # Attach to the main router so main.py picks it up
    try:
        router.include_router(_bandit_router)
    except Exception:
        pass
except Exception:
    # Never break startup if optional endpoints fail
    pass
