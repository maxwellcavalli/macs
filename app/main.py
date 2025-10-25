from __future__ import annotations
from fastapi import FastAPI
from .sse_early_exit_mw import SSEEarlyExitMiddleware
from fastapi.middleware.cors import CORSMiddleware
from .api import router, hub
from .bandit_ui import router as bandit_ui_router
import app.bandit_ui  # registers /bandit and /v1/bandit/observations

from .queue import JobQueue
from .logging_setup import setup_json_logging, get_logger
from .middleware import RequestIDMiddleware

setup_json_logging()
log = get_logger("bootstrap")

app = FastAPI(title="MACS API")



# Early-exit SSE when artifacts already exist
app.add_middleware(SSEEarlyExitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)
app.add_middleware(RequestIDMiddleware)

app.include_router(router)
app.include_router(bandit_ui_router)

@app.on_event("startup")
async def _startup():
    # create and start the queue
    jobq = JobQueue(hub)
    await jobq.start()
    # expose via app.state (authoritative)
    app.state.job_queue = jobq
    # also set module global for older call sites
    from . import api as api_module
    api_module.job_queue = jobq
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


def _resolve_pg_dsn() -> str | None:
    import os
    dsn = os.getenv("BANDIT_PG_DSN")
    if dsn: return dsn
    host = os.getenv("PGHOST") or os.getenv("POSTGRES_HOST")
    user = os.getenv("PGUSER") or os.getenv("POSTGRES_USER")
    pwd  = os.getenv("PGPASSWORD") or os.getenv("POSTGRES_PASSWORD") or ""
    db   = os.getenv("PGDATABASE") or os.getenv("POSTGRES_DB")
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
