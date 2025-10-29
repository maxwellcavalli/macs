from __future__ import annotations
import asyncio
class BodySizeLimitASGI:
    """ASGI wrapper enforcing max HTTP request body size (default 10MiB)."""
    def __init__(self, app, max_bytes=None):
        import os
        self.app = app
        self.max = int(max_bytes) if max_bytes is not None else int(os.getenv("MACS_MAX_BODY_BYTES", "10485760"))
    def __getattr__(self, name):
        # delegate attributes so add_middleware etc. still work
        return getattr(self.app, name)
    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)
        # Content-Length fast path
        try:
            cl = None
            for k, v in scope.get("headers", []):
                if k == b"content-length":
                    cl = int(v.decode("latin1")); break
            if cl is not None and cl > self.max:
                await send({"type":"http.response.start","status":413,"headers":[(b"content-type",b"application/json")]})
                await send({"type":"http.response.body","body":('{"error":"request_too_large","limit_bytes":%d,"content_length":%d}' % (self.max, cl)).encode()})
                return
        except Exception:
            pass
        # Streaming path
        bytes_seen = 0; done = False
        async def limited_receive():
            nonlocal bytes_seen, done
            message = await receive()
            if message.get("type") == "http.request":
                body = message.get("body", b"") or b""
                bytes_seen += len(body)
                if bytes_seen > self.max and not done:
                    done = True
                    await send({"type":"http.response.start","status":413,"headers":[(b"content-type",b"application/json")]})
                    await send({"type":"http.response.body","body":('{"error":"request_too_large","limit_bytes":%d,"content_length":%d}' % (self.max, bytes_seen)).encode()})
                    return {"type":"http.disconnect"}
            return message
        return await self.app(scope, limited_receive, send)

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from .otel_inline import enable_otel_headers  # INLINE_OTEL_PATCH_v1
from .sse_early_exit_mw import SSEEarlyExitMiddleware
from fastapi.middleware.cors import CORSMiddleware
from .api import router, hub
from .bandit_stats_api import router as bandit_stats_router
from .bandit_ui import router as bandit_ui_router
import app.bandit_ui  # registers /bandit and /v1/bandit/observations
from .queue import JobQueue
from .db import init_db
from .logging_setup import setup_json_logging, get_logger
from .middleware import RequestIDMiddleware
from .registry import available_models
from .llm.ollama_client import ensure_model, OllamaError
from .settings import settings
setup_json_logging()
log = get_logger("bootstrap")
app = FastAPI(title="MACS API")

# Serve Tailwind Prompt Lab at /lab
app.mount("/lab", StaticFiles(directory="app/static/lab", html=True), name="lab")
# Serve chat UI at /chat
app.mount("/chat", StaticFiles(directory="app/static/chat", html=True), name="chat")
enable_otel_headers(app)  # INLINE_OTEL_PATCH_v1
# Early-exit SSE when artifacts already exist
app.add_middleware(SSEEarlyExitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)
app.add_middleware(RequestIDMiddleware)
app.include_router(router)
app.include_router(bandit_stats_router)
app.include_router(bandit_ui_router)
@app.on_event("startup")
async def _startup():
    try:
        await init_db()
        log.info("db.init_ok")
    except Exception as exc:
        log.error("db.init_failed", {"err": str(exc)})
        raise
    await _ensure_primary_models()
    # create and start the queue
    jobq = JobQueue(hub)
    await jobq.start()
    # expose via app.state (authoritative)
    app.state.job_queue = jobq
    # also set module global for older call sites
    from . import api as api_module
    api_module.job_queue = jobq
    asyncio.create_task(_warm_default_models())
    log.info("startup complete")
@app.get("/")
async def root():
    return {"ok": True, "service": "macs-api"}
# --- Bandit endpoints mounted on the FastAPI app (app-level) ---
try:
    from fastapi import HTTPException, Request
    from .bandit_store import record_event as _bandit_record_event, get_stats as _bandit_get_stats
    _app = globals().get("app")
    if _app is not None:
        async def _bandit_record(payload: dict):
            model = str(payload.get("model") or "unknown")
            try:
                reward = float(payload.get("reward"))
            except Exception:
                raise HTTPException(status_code=422, detail="reward must be a number")
            meta = payload.get("meta") or {}
            _bandit_record_event(model, reward, meta)
            return {"ok": True}
        async def _bandit_stats():
            return {"ok": True, "stats": _bandit_get_stats()}
        async def __debug_routes(request: Request):
            return {"routes": [getattr(r, "path", None) for r in request.app.routes]}
        _app.add_api_route("/v1/bandit/record", _bandit_record, methods=["POST"])
        _app.add_api_route("/v1/bandit/stats", _bandit_stats, methods=["GET"])
        _app.add_api_route("/v1/__debug/routes", __debug_routes, methods=["GET"])
except Exception:
    # Never break startup if optional endpoints fail
    pass
# --- Simple DUEL submit endpoint (compat layer for local testing) ---
import os, json, uuid, threading, time
from pathlib import Path
from typing import Any, Dict, List
from fastapi import HTTPException
try:
    from .bandit_store import record_event as _bandit_record_event  # best-effort import
except Exception:
    _bandit_record_event = None  # type: ignore
_DUEL_ART_DIR = os.getenv("ARTIFACTS_DIR", "/data/artifacts")
def _duel_worker(task_id: str, prompt: str, models: List[str]) -> None:
    # Simulate scoring & persist bandit events
    for idx, m in enumerate(models):
        reward = 1.0 if idx == 0 else 0.5  # demo weights; adjust as needed
        try:
            if _bandit_record_event is not None:
                _bandit_record_event(m, reward, {"src": "duel_stub", "prompt": prompt})
        except Exception:
            pass
        time.sleep(0.05)
    # Write an artifact to trigger SSE early-exit (your middleware will detect the dir)
    root = Path(_DUEL_ART_DIR) / task_id
    root.mkdir(parents=True, exist_ok=True)
    (root / "result.json").write_text(
        json.dumps({"ok": True, "task_id": task_id, "prompt": prompt, "models": models}, ensure_ascii=False),
        encoding="utf-8"
    )
# Mounted on the actual FastAPI app
_app = globals().get("app")
if _app is not None:
    async def _duel_submit(payload: Dict[str, Any]):
        # Accept several shapes: {prompt, models}, {prompt, candidates:[{model}]}, or {input:{...}}
        prompt = (
            (payload.get("input") or {}).get("prompt")
            or payload.get("prompt")
            or (payload.get("goal") or "No prompt provided")
        )
        models: List[str] = []
        if "models" in payload:
            try:
                models = [str(x) for x in payload["models"] if x]
            except Exception:
                pass
        if not models and "candidates" in payload:
            try:
                models = [str(c.get("model")) for c in payload["candidates"] if c.get("model")]
            except Exception:
                pass
        if not models:
            raise HTTPException(status_code=422, detail="Provide models: ['modelA','modelB'] or candidates:[{model:...}]")
        if len(models) < 2:
            raise HTTPException(status_code=422, detail="At least two models required for duel")
        task_id = str(uuid.uuid4())
        threading.Thread(target=_duel_worker, args=(task_id, prompt, models), daemon=True).start()
        return {"task_id": task_id}
    _app.add_api_route("/v1/duel", _duel_submit, methods=["POST"])
# --- Bandit debug endpoint ---
import os, json
from pathlib import Path
from typing import Any, Dict
_app = globals().get("app")
if _app is not None:
    async def _bandit_debug() -> Dict[str, Any]:
        env_path = os.getenv("BANDIT_STORE_PATH", "/data/bandit/bandit.jsonl")
        p = Path(env_path)
        exists = p.exists()
        size = p.stat().st_size if exists else 0
        tail = []
        if exists:
            try:
                with p.open("r", encoding="utf-8") as f:
                    lines = f.readlines()
                tail = [l.strip() for l in lines[-2:]]
            except Exception as e:
                tail = [f"<read-error: {e}>"]
        return {"env_path": env_path, "exists": exists, "size": size, "tail": tail}
    _app.add_api_route("/v1/bandit/debug", _bandit_debug, methods=["GET"])
# --- Bandit force-write/debug endpoint ---
from typing import Any, Dict
try:
    from .bandit_store import record_event as _be_record, get_stats as _be_stats, get_store_path as _be_path
    _app = globals().get("app")
    if _app is not None:
        async def _bandit_force(payload: Dict[str, Any] | None = None):
            payload = payload or {}
            model = str((payload.get("model") or "force-model"))
            reward = float(payload.get("reward") or 0.777)
            path = _be_record(model, reward, {"src": "force-endpoint"})
            p = Path(path)
            exists = p.exists()
            size = p.stat().st_size if exists else 0
            tail = []
            if exists:
                with p.open("r", encoding="utf-8") as f:
                    lines = f.readlines()
                tail = [l.strip() for l in lines[-2:]]
            return {"path": path, "exists": exists, "size": size, "tail": tail, "stats_after": _be_stats()}
        _app.add_api_route("/v1/bandit/force", _bandit_force, methods=["POST", "GET"])
except Exception:
    pass
# --- Bandit export endpoint (csv/jsonl) ---
from typing import Optional
from fastapi import Query
from fastapi.responses import Response
try:
    from .bandit_store import get_store_path as _be_path
    import json, datetime
    _app = globals().get("app")
    if _app is not None:
        async def _bandit_export(fmt: str = Query(default="csv", pattern="^(csv|jsonl|ndjson)$"),
                                 download: Optional[int] = 0):
            path = _be_path()
            try:
                with open(path, "r", encoding="utf-8") as f:
                    lines = [ln.rstrip("\n") for ln in f]
            except FileNotFoundError:
                lines = []
            if fmt in ("jsonl","ndjson"):
                body = "\n".join(lines) + ("\n" if lines else "")
                headers = {}
                if download:
                    headers["Content-Disposition"] = 'attachment; filename="bandit.jsonl"'
                return Response(content=body, media_type="application/x-ndjson", headers=headers)
            # csv
            rows = ["ts_iso,model,reward,meta_json"]
            for ln in lines:
                if not ln.strip():
                    continue
                try:
                    ev = json.loads(ln)
                except Exception:
                    continue
                ts = ev.get("ts", 0)
                ts_iso = datetime.datetime.utcfromtimestamp(float(ts)).isoformat() + "Z"
                model = str(ev.get("model","unknown")).replace('"','""')
                reward = ev.get("reward",0)
                meta_json = json.dumps(ev.get("meta", {}), ensure_ascii=False).replace('"','""')
                rows.append(f'{ts_iso},"{model}",{reward},"{meta_json}"')
            body = "\n".join(rows) + "\n"
            headers = {}
            if download:
                headers["Content-Disposition"] = 'attachment; filename="bandit.csv"'
            return Response(content=body, media_type="text/csv; charset=utf-8", headers=headers)
        _app.add_api_route("/v1/bandit/export", _bandit_export, methods=["GET"])
except Exception:
    pass
# --- SSE route: /v1/tasks/{task_id}/stream (artifact-aware) ---
import os, json, time
from pathlib import Path
from fastapi.responses import StreamingResponse
def _sse_event(obj) -> bytes:
    try:
        return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n".encode("utf-8")
    except Exception:
        return b"data: {\"status\":\"error\",\"note\":\"json-dump\"}\n\n"
def _artifact_root(task_id: str) -> Path:
    base = os.getenv("ARTIFACTS_DIR", "/app/artifacts")
    return Path(base) / task_id
def _stream_gen(task_id: str):
    root = _artifact_root(task_id)
    # Immediate early-exit if artifacts already present
    try:
        if root.exists() and root.is_dir():
            yield _sse_event({"status":"done","note":"artifacts-present"})
            return
    except Exception:
        pass
    # Keepalive loop (30s): half-second pings, exit when artifacts appear
    for _ in range(60):
        try:
            if root.exists() and root.is_dir():
                yield _sse_event({"status":"done","note":"artifacts-present"})
                return
        except Exception:
            pass
        # comment line keeps the connection alive without spamming JSON
        yield b": keep-alive\n\n"
        time.sleep(0.5)
    # Timed out without artifacts
    yield _sse_event({"status":"timeout","note":"no-artifacts"})
    return
_app = globals().get("app")
if _app is not None:
    def _tasks_stream(task_id: str):
        return StreamingResponse(_stream_gen(task_id), media_type="text/event-stream")
    _app.add_api_route("/v1/tasks/{task_id}/stream", _tasks_stream, methods=["GET"])
# --- Attach SSE+status router (idempotent) ---
try:
    from .sse_routes import router as _sse_router  # type: ignore
    app.include_router(_sse_router)
except Exception:
    pass
async def _warm_default_models() -> None:
    """
    Background warm-up that pre-ensures a small set of frequently-used models.
    Executes best-effort and never blocks app startup.
    """
    await asyncio.sleep(0)  # yield to finish startup work
    try:
        preferred: set[str] = set()
        if settings.chat_mode_default:
            preferred.add(settings.chat_mode_default.strip())
        warm_languages = [None, "docs", "planner", "java", "python"]
        for lang in warm_languages:
            try:
                candidates = available_models(lang)
            except Exception:
                continue
            for meta in candidates[:2]:
                tag = (
                    str(meta.get("tag") or "")
                    or str(meta.get("model") or "")
                ).strip()
                if not tag:
                    name = str(meta.get("name") or "").strip()
                    size = str(meta.get("size") or "").strip()
                    quant = str(meta.get("quant") or "").strip()
                    if name:
                        tag = name
                        if size:
                            tag = f"{tag}:{size}"
                        if quant:
                            if not tag.endswith(quant):
                                tag = f"{tag}-{quant}"
                if tag:
                    preferred.add(tag)
        if not preferred:
            return
        log.info("model.warmup.start", {"models": sorted(preferred)})
        for tag in sorted(preferred):
            if tag in _READY_MODELS:
                continue
            try:
                await ensure_model(tag)
                _READY_MODELS.add(tag)
                log.info("model.warmup.ok", {"model": tag})
            except OllamaError as exc:
                log.warning("model.warmup.ollama_error", {"model": tag, "err": str(exc)})
            except Exception as exc:
                log.warning("model.warmup.failed", {"model": tag, "err": str(exc)})
    except asyncio.CancelledError:
        log.info("model.warmup.cancelled")
        raise
    except Exception as exc:
        log.warning("model.warmup.unexpected_error", {"err": str(exc)})
_READY_MODELS: set[str] = set()

async def _ensure_primary_models() -> None:
    """
    Ensure the primary chat model is available before the queue starts,
    so first requests do not block on an Ollama pull.
    """
    primary = (settings.chat_mode_default or "").strip()
    if not primary:
        return
    try:
        log.info("model.ensure.start", {"model": primary})
        await ensure_model(primary)
        _READY_MODELS.add(primary)
        log.info("model.ensure.ready", {"model": primary})
    except OllamaError as exc:
        log.warning("model.ensure.ollama_error", {"model": primary, "err": str(exc)})
    except Exception as exc:
        log.warning("model.ensure.failed", {"model": primary, "err": str(exc)})
def _resolve_pg_dsn() -> str | None:
    import os
    dsn = os.getenv("BANDIT_PG_DSN") or os.getenv("DATABASE_URL")
    if dsn:
        if dsn.startswith("postgresql+"):
            dsn = "postgresql://" + dsn.split("://", 1)[1]
        return dsn
    host = os.getenv("PGHOST") or os.getenv("POSTGRES_HOST") or "postgres"
    user = os.getenv("PGUSER") or os.getenv("POSTGRES_USER") or "postgres"
    pwd  = os.getenv("PGPASSWORD") or os.getenv("POSTGRES_PASSWORD") or ""
    db   = os.getenv("PGDATABASE") or os.getenv("POSTGRES_DB") or os.getenv("DB_NAME")
    port = os.getenv("PGPORT") or os.getenv("POSTGRES_PORT") or "5432"
    if host and user and db:
        return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"
    return None
@app.on_event("startup")
async def _init_bandit_store():
    import logging
    from .bandit_store_pg import BanditStorePG
    dsn = _resolve_pg_dsn()
    if not dsn:
        logging.getLogger(__name__).warning("Bandit store disabled: no Postgres DSN found in env")
        return
    try:
        pool_min = int(os.getenv("BANDIT_POOL_MIN", "1"))
        pool_max = int(os.getenv("BANDIT_POOL_MAX", "8"))
        app.state.bandit_store = BanditStorePG(dsn, min_size=pool_min, max_size=pool_max)
        logging.getLogger(__name__).info("Bandit store initialized with Postgres")
    except Exception as e:
        logging.getLogger(__name__).exception("Bandit store init failed: %s", e)
        app.state.bandit_store = None
def create_app():
    """
    Uvicorn factory entrypoint that returns the app wrapped by the size limiter.
    Returns an ASGI callable. Safe if limiter import fails.
    """
    try:
        wrapped = BodySizeLimitASGI(app)
    except Exception:
        wrapped = app
    return wrapped
# --- include final endpoint (safe import placed at end) ---
try:
    from .final_api import router as _final_router
    app.include_router(_final_router)
except Exception as _e:
    # keep server booting even if optional module is missing
    pass

# --- include artifact ensure endpoint ---
try:
    from .artifact_api import router as _artifact_router
    app.include_router(_artifact_router)
    print("[startup] /v1/tasks/{id}/ensure_artifact enabled")
except Exception as _e:
    print("[startup] artifact_api not enabled:", _e)

# --- attach a minimal asyncpg task_repo from env (if none present) ---
try:
    if not getattr(app.state, "task_repo", None):
        from .task_repo import TaskRepo
        app.state.task_repo = TaskRepo.from_env()
        print("[startup] task_repo enabled (asyncpg)")
except Exception as _e:
    print("[startup] task_repo not enabled:", _e)

# --- include JSON-safe /final endpoint (if present) ---
try:
    from .final_api import router as _final_router
    app.include_router(_final_router)
    print("[startup] /v1/tasks/{id}/final enabled")
except Exception as _e:
    print("[startup] final_api not enabled:", _e)

# --- include ensure_artifact endpoint (if present) ---
try:
    from .artifact_api import router as _artifact_router
    app.include_router(_artifact_router)
    print("[startup] /v1/tasks/{id}/ensure_artifact enabled")
except Exception as _e:
    print("[startup] artifact_api not enabled:", _e)

# --- Canonical status middlewares (JSON + SSE) ---
try:
    from .middleware_canon import JSONCanonicalizerMiddleware, SSECanonicalizerMiddleware
    if not getattr(app.state, "_canon_mw_installed", False):
        app.add_middleware(JSONCanonicalizerMiddleware)
        app.add_middleware(SSECanonicalizerMiddleware)
        app.state._canon_mw_installed = True
        print("[startup] Canonical status middlewares enabled")
except Exception as _e:
    print("[startup] Canonical status middlewares NOT enabled:", _e)
