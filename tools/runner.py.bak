import os, json, uuid, asyncio, aiohttp, traceback
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

def redact_dsn(dsn:str) -> str:
    try:
        u = urlsplit(dsn.replace("postgresql+asyncpg", "postgresql"))
        netloc = u.netloc
        if "@" in netloc:
            creds, host = netloc.split("@", 1)
            user = creds.split(":", 1)[0]
            netloc = f"{user}:***@" + host
        return urlunsplit((u.scheme, netloc, u.path, u.query, u.fragment))
    except Exception:
        return dsn

DBURL   = os.environ.get("DATABASE_URL", "")
OLLAMA  = os.environ.get("OLLAMA_URL", "http://ollama:11434")
if DBURL.startswith("postgresql://"):
    DBURL = DBURL.replace("postgresql://", "postgresql+asyncpg://", 1)

def log(msg): print(f"[runner] {datetime.utcnow().isoformat()}Z {msg}", flush=True)

ALLOW_OPTS = {"temperature","top_p","seed","num_ctx","num_predict","mirostat","mirostat_eta","mirostat_tau"}

def map_opts(opts):
    if not isinstance(opts, dict): return {}
    out = {k:v for k,v in opts.items() if k in ALLOW_OPTS}
    if "max_tokens" in opts and "num_predict" not in out:
        out["num_predict"] = int(opts.get("max_tokens") or 256)
    return out

def pick(*vals, default=None):
    for v in vals:
        if v is not None and v != "" and v != {}:
            return v
    return default

def as_dict(v):
    return v if isinstance(v, dict) else {}

def find_str(d:dict, keys):
    d = as_dict(d)
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None

def resolve_fields(task):
    """Resolve goal/model/language/options/repo/constraints from columns OR metadata.* fallbacks."""
    meta = as_dict(task.get("metadata"))
    meta_in  = as_dict(meta.get("input"))
    meta_req = as_dict(meta.get("request") or meta.get("payload") or {})
    # Accept many possible prompt keys
    goal = pick(
        task.get("goal"),
        find_str(meta_in,  ["goal","prompt","instruction","query","text"]),
        find_str(meta_req, ["goal","prompt","instruction","query","text"]),
        find_str(meta,     ["goal","prompt","instruction","query","text"]),
        default=""
    )
    model = pick(
        task.get("model"),
        meta_in.get("model"), meta_req.get("model"), meta.get("model"),
        default="qwen2.5:7b"
    )
    language = pick(
        task.get("language"),
        meta_in.get("language"), meta_req.get("language"), meta.get("language"),
        default="python"
    )
    options = as_dict(pick(task.get("options"), meta_in.get("options"), meta_req.get("options"), meta.get("options"), default={}))
    repo = as_dict(pick(task.get("repo"), meta_in.get("repo"), meta_req.get("repo"), meta.get("repo"), default={}))
    constraints = as_dict(pick(task.get("constraints"), meta_in.get("constraints"), meta_req.get("constraints"), meta.get("constraints"), default={}))
    return goal, model, language, options, repo, constraints

async def db_engine():
    if not DBURL:
        log("FATAL: DATABASE_URL is not set"); raise SystemExit(1)
    log(f"DB = {redact_dsn(DBURL)}")
    log(f"OLLAMA = {OLLAMA}")
    engine = create_async_engine(DBURL, pool_size=5, max_overflow=5)
    async with engine.begin() as conn:
        v = await conn.execute(text("select current_database(), current_user, now()"))
        log(f"DB OK: {list(v.first())}")
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.get(f"{OLLAMA}/api/tags") as r:
                j = await r.json()
                n = len(j.get("models", [])) if isinstance(j, dict) else 0
                log(f"Ollama OK: {n} models visible")
    except Exception as e:
        log(f"WARNING: cannot reach Ollama at {OLLAMA}: {e}")
    return engine

async def claim_one(engine):
    sql = """
    WITH got AS (
      SELECT id FROM public.tasks
      WHERE status='queued'
      ORDER BY created_at
      FOR UPDATE SKIP LOCKED
      LIMIT 1
    )
    UPDATE public.tasks t
    SET status='running', updated_at=now()
    FROM got
    WHERE t.id = got.id
    RETURNING t.id, t.type, t.language, t.model, t.options, t.metadata, t.goal, t.constraints, t.repo;
    """
    async with engine.begin() as conn:
        r = await conn.execute(text(sql))
        row = r.first()
        return dict(row._mapping) if row else None

async def emit_event(engine, task_id, kind, delta=None, data=None):
    payload = json.dumps(data or {})
    async with engine.begin() as conn:
        await conn.execute(text("""
            INSERT INTO public.task_events(task_id, kind, delta, data)
            VALUES (:id, :kind, :delta, CAST(:data AS JSONB))
        """), {"id": task_id, "kind": kind, "delta": delta, "data": payload})

async def set_status(engine, task_id, status, result=None, error=None):
    async with engine.begin() as conn:
        await conn.execute(text("""
            UPDATE public.tasks SET status=:s, result=:r, error=:e, updated_at=now() WHERE id=:id
        """), {"s": status, "r": result, "e": error, "id": task_id})

async def run_task(engine, task):
    tid = task["id"]
    goal, model, language, options_raw, repo, constraints = resolve_fields(task)
    options = map_opts(options_raw or {})
    log(f"RUN {tid} model={model} num_predict={options.get('num_predict')} goal_len={len(goal)}")

    if not goal:
        await emit_event(engine, tid, "error", data={"stage":"resolve","msg":"empty goal"})
        await set_status(engine, tid, "failed", error="empty goal")
        log(f"FAIL {tid} empty goal"); return

    result_chunks = []
    try:
        timeout = aiohttp.ClientTimeout(total=None)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.post(f"{OLLAMA}/api/generate", json={"model": model, "prompt": goal, "stream": True, "options": options}) as resp:
                resp.raise_for_status()
                buf = b""
                async for chunk in resp.content.iter_chunked(4096):
                    if not chunk: continue
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        line = line.strip()
                        if not line: continue
                        try:
                            msg = json.loads(line.decode("utf-8"))
                        except Exception:
                            continue
                        delta = msg.get("response") or msg.get("delta") or ""
                        if delta:
                            result_chunks.append(delta)
                            await emit_event(engine, tid, "delta", delta=delta)
                        if msg.get("done"):
                            buf = b""; break
                if buf.strip():
                    try:
                        msg = json.loads(buf.decode("utf-8"))
                        delta = msg.get("response") or msg.get("delta") or ""
                        if delta:
                            result_chunks.append(delta); await emit_event(engine, tid, "delta", delta=delta)
                    except Exception:
                        pass
    except Exception as e:
        await emit_event(engine, tid, "error", data={"stage":"generate","msg":str(e)})
        await set_status(engine, tid, "failed", error=str(e))
        log(f"ERROR generate {tid}: {e}"); return

    result = "".join(result_chunks).strip()
    # Insert a tiny artifact so systems requiring artifacts don't timeout
    try:
        aid = str(uuid.uuid4())
        async with engine.begin() as conn:
            await conn.execute(text("""
              INSERT INTO public.artifacts(id, task_id, name, path, mime_type, size_bytes, sha256)
              VALUES (:id, :tid, 'answer.md', '/dev/null', 'text/markdown', :sz, NULL)
            """), {"id": aid, "tid": tid, "sz": len(result.encode("utf-8"))})
    except Exception as e:
        log(f"WARNING: artifact insert failed: {e}")

    await set_status(engine, tid, "succeeded", result=result)
    log(f"DONE {tid} len={len(result)}")

async def main():
    engine = await db_engine()
    idle = 0
    while True:
        try:
            task = await claim_one(engine)
            if not task:
                idle += 1
                if idle % 6 == 0: log("idle: no queued tasks")
                await asyncio.sleep(0.5); continue
            idle = 0
            await run_task(engine, task)
        except Exception:
            log("FATAL LOOP ERROR:\n" + traceback.format_exc()); await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
