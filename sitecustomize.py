import os, sys, traceback, re

MODE = os.getenv("STATUS_GUARD_MODE", "error").lower()  # error|warn|fix|off
if MODE not in {"error","warn","fix","off"}:
    MODE = "error"
if MODE == "off":
    raise SystemExit(0)

BAD2CANON = {
    "succeeded":"done","success":"done","completed":"done","complete":"done",
    "failed":"error","failure":"error","fail":"error",
    "cancelled":"canceled",
}
RE_BAD = re.compile(r"\b(succeeded|success|completed|complete|failed|failure|fail|cancelled)\b", re.I)

def _canon(v: str) -> str:
    s = (v or "").strip().lower()
    return BAD2CANON.get(s, s)

def _log(tag: str, detail: str):
    print(f"[status-guard] {tag}: {detail!r}", file=sys.stderr)
    print("".join(traceback.format_stack(limit=14)), file=sys.stderr)

def _should_check_sql(stmt: str) -> bool:
    s = (stmt or "").lower()
    return (" update " in s or " insert " in s) and " status" in s and " tasks" in s

def _check_values(vals):
    for v in vals:
        if isinstance(v, str) and v.strip().lower() in BAD2CANON:
            return v
    return None

# ---------------- SQLAlchemy (ORM/Core) ----------------
try:
    import sqlalchemy as sa
    from sqlalchemy import event
    from sqlalchemy.orm import Session
    from sqlalchemy.engine import Engine
    @event.listens_for(Session, "before_flush")
    def _sa_before_flush(session, ctx, instances):
        for obj in list(session.new) + list(session.dirty):
            try:
                val = getattr(obj, "status", None)
                tn = getattr(obj, "__tablename__", "") or getattr(getattr(obj, "__table__", None), "name", "")
            except Exception:
                continue
            if not isinstance(val, str): continue
            low = val.strip().lower()
            if low in BAD2CANON and (not tn or tn == "tasks"):
                if MODE == "fix":
                    setattr(obj, "status", _canon(val)); _log("FIXED on flush", f"{tn}:{val}")
                elif MODE == "warn":
                    _log("WARN on flush", f"{tn}:{val}")
                else:
                    _log("ERROR on flush", f"{tn}:{val}"); raise ValueError(f"non-canonical status: {val!r}")
    @event.listens_for(Engine, "before_cursor_execute", retval=True)
    def _sa_before_exec(conn, cursor, statement, parameters, context, executemany):
        if not _should_check_sql(statement):
            return statement, parameters
        bad = RE_BAD.search((statement or "").lower()) is not None
        if not bad:
            try:
                items = parameters if executemany and isinstance(parameters, (list, tuple)) else [parameters]
                for row in items:
                    vals = row.values() if isinstance(row, dict) else (row if isinstance(row, (list, tuple)) else [])
                    if _check_values(vals):
                        bad = True; break
            except Exception:
                pass
        if bad:
            if MODE == "fix":
                try:
                    def fx(x): return BAD2CANON.get(x.strip().lower(), x) if isinstance(x, str) else x
                    if isinstance(parameters, dict): parameters = {k: fx(v) for k,v in parameters.items()}
                    elif isinstance(parameters, (list, tuple)):
                        if executemany:
                            parameters = [tuple(fx(v) for v in row) if isinstance(row, (list, tuple)) else row for row in parameters]  # type: ignore
                        else:
                            parameters = tuple(fx(v) for v in parameters)  # type: ignore
                    _log("FIXED in SQLAlchemy SQL", (statement or "")[:200])
                except Exception:
                    _log("WARN (could-not-fix) SQLAlchemy SQL", (statement or "")[:200])
            elif MODE == "warn":
                _log("WARN in SQLAlchemy SQL", (statement or "")[:200])
            else:
                _log("ERROR in SQLAlchemy SQL", (statement or "")[:200]); raise ValueError("non-canonical status in SQL")
        return statement, parameters
except Exception:
    pass  # SQLAlchemy not used

# ---------------- asyncpg ----------------
def _patch_asyncpg():
    try:
        import asyncpg  # type: ignore
    except Exception:
        return
    # wrap connection object
    class _ConnProxy:
        __slots__ = ("_c",)
        def __init__(self, c): self._c = c
        def __getattr__(self, n): return getattr(self._c, n)
        async def execute(self, statement, *args, **kw):
            if _should_check_sql(statement):
                bad = bool(RE_BAD.search((statement or "").lower())) or _check_values(args) or _check_values(kw.values() if kw else [])
                if bad:
                    if MODE == "fix":
                        args = tuple(_canon(a) if isinstance(a, str) else a for a in args)
                        if kw: kw = {k: (_canon(v) if isinstance(v, str) else v) for k,v in kw.items()}
                        _log("FIXED in asyncpg.execute", (statement or "")[:200])
                    elif MODE == "warn":
                        _log("WARN in asyncpg.execute", (statement or "")[:200])
                    else:
                        _log("ERROR in asyncpg.execute", (statement or "")[:200]); raise ValueError("non-canonical status in SQL")
            return await self._c.execute(statement, *args, **kw)
        async def executemany(self, statement, args, *a, **kw):
            if _should_check_sql(statement):
                bad = False
                for row in (args or []):
                    if _check_values(row): bad=True; break
                if bad:
                    if MODE == "fix":
                        args = [tuple(_canon(v) if isinstance(v, str) else v for v in row) for row in args]
                        _log("FIXED in asyncpg.executemany", (statement or "")[:200])
                    elif MODE == "warn":
                        _log("WARN in asyncpg.executemany", (statement or "")[:200])
                    else:
                        _log("ERROR in asyncpg.executemany", (statement or "")[:200]); raise ValueError("non-canonical status in SQL")
            return await self._c.executemany(statement, args, *a, **kw)
    # patch connect/create_pool
    _orig_connect = getattr(asyncpg, "connect", None)
    _orig_create_pool = getattr(asyncpg, "create_pool", None)
    async def _wrap_connect(*a, **kw):
        c = await _orig_connect(*a, **kw)
        return _ConnProxy(c)
    async def _wrap_acquire(pool, *a, **kw):
        c = await pool._acquire(*a, **kw)
        return _ConnProxy(c)
    async def _wrap_create_pool(*a, **kw):
        pool = await _orig_create_pool(*a, **kw)
        try:
            pool._acquire = _wrap_acquire.__get__(pool, type(pool))  # monkey-patch acquire
        except Exception:
            pass
        return pool
    if _orig_connect:
        asyncpg.connect = _wrap_connect  # type: ignore
    if _orig_create_pool:
        asyncpg.create_pool = _wrap_create_pool  # type: ignore

# ---------------- psycopg / psycopg2 ----------------
def _patch_psycopg():
    # psycopg 3
    try:
        import psycopg as _pg3  # type: ignore
        from psycopg.rows import Row  # noqa
        def _wrap_cursor(cur):
            _exec = cur.execute; _execm = cur.executemany
            def _do_exec(stmt, *args, **kw):
                s = stmt.decode() if isinstance(stmt, (bytes, bytearray)) else stmt
                if _should_check_sql(s):
                    bad = bool(RE_BAD.search((s or "").lower())) or _check_values(args) or _check_values(kw.values() if kw else [])
                    if bad:
                        if MODE == "fix":
                            args = tuple(_canon(a) if isinstance(a, str) else a for a in args)
                            if kw: kw = {k: (_canon(v) if isinstance(v, str) else v) for k,v in kw.items()}
                            _log("FIXED in psycopg3.execute", (s or "")[:200])
                        elif MODE == "warn":
                            _log("WARN in psycopg3.execute", (s or "")[:200])
                        else:
                            _log("ERROR in psycopg3.execute", (s or "")[:200]); raise ValueError("non-canonical status in SQL")
                return _exec(s, *args, **kw)
            def _do_execm(stmt, params):
                s = stmt.decode() if isinstance(stmt, (bytes, bytearray)) else stmt
                if _should_check_sql(s):
                    bad = any(_check_values(row) for row in (params or []))
                    if bad:
                        if MODE == "fix":
                            params = [tuple(_canon(v) if isinstance(v, str) else v for v in row) for row in params]
                            _log("FIXED in psycopg3.executemany", (s or "")[:200])
                        elif MODE == "warn":
                            _log("WARN in psycopg3.executemany", (s or "")[:200])
                        else:
                            _log("ERROR in psycopg3.executemany", (s or "")[:200]); raise ValueError("non-canonical status in SQL")
                return _execm(s, params)
            cur.execute = _do_exec  # type: ignore
            cur.executemany = _do_execm  # type: ignore
            return cur
        _orig_conn = _pg3.connect
        def _wrap_connect(*a, **kw):
            conn = _orig_conn(*a, **kw)
            _orig_cursor = conn.cursor
            def _wrap_cursor_factory(*aa, **kk):
                return _wrap_cursor(_orig_cursor(*aa, **kk))
            conn.cursor = _wrap_cursor_factory  # type: ignore
            return conn
        _pg3.connect = _wrap_connect  # type: ignore
    except Exception:
        pass
    # psycopg2
    try:
        import psycopg2 as _pg2  # type: ignore
        _orig_connect2 = _pg2.connect
        def _wrap_connect2(*a, **kw):
            conn = _orig_connect2(*a, **kw)
            _orig_cursor = conn.cursor
            def _wrap_cursor_factory(*aa, **kk):
                cur = _orig_cursor(*aa, **kk)
                _exec = cur.execute; _execm = cur.executemany
                def _do_exec(stmt, *args):
                    s = stmt.decode() if isinstance(stmt, (bytes, bytearray)) else stmt
                    if _should_check_sql(s):
                        bad = bool(RE_BAD.search((s or "").lower())) or _check_values(args)
                        if bad:
                            if MODE == "fix":
                                args = tuple(_canon(a) if isinstance(a, str) else a for a in args)
                                _log("FIXED in psycopg2.execute", (s or "")[:200])
                            elif MODE == "warn":
                                _log("WARN in psycopg2.execute", (s or "")[:200])
                            else:
                                _log("ERROR in psycopg2.execute", (s or "")[:200]); raise ValueError("non-canonical status in SQL")
                    return _exec(s, *args)
                def _do_execm(stmt, params):
                    s = stmt.decode() if isinstance(stmt, (bytes, bytearray)) else stmt
                    if _should_check_sql(s):
                        bad = any(_check_values(row) for row in (params or []))
                        if bad:
                            if MODE == "fix":
                                params = [tuple(_canon(v) if isinstance(v, str) else v for v in row) for row in params]
                                _log("FIXED in psycopg2.executemany", (s or "")[:200])
                            elif MODE == "warn":
                                _log("WARN in psycopg2.executemany", (s or "")[:200])
                            else:
                                _log("ERROR in psycopg2.executemany", (s or "")[:200]); raise ValueError("non-canonical status in SQL")
                    return _execm(s, params)
                cur.execute = _do_exec  # type: ignore
                cur.executemany = _do_execm  # type: ignore
                return cur
            conn.cursor = _wrap_cursor_factory  # type: ignore
            return conn
        _pg2.connect = _wrap_connect2  # type: ignore
    except Exception:
        pass

# activate driver patches
_patch_asyncpg()
_patch_psycopg()
