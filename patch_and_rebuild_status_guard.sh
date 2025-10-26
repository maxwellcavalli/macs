#!/usr/bin/env bash
set -Eeuo pipefail

# 1) Drop the guard that canonicalizes/logs status writes at runtime
cat > sitecustomize.py <<'PY'
import os, sys, traceback, re
MODE = os.getenv("STATUS_GUARD_MODE", "error").lower()  # error|warn|fix|off
if MODE not in {"error","warn","fix","off"}:
    MODE = "error"
if MODE == "off":
    raise SystemExit(0)
try:
    import sqlalchemy as sa
    from sqlalchemy import event
    from sqlalchemy.orm import Session
    from sqlalchemy.engine import Engine
except Exception:
    raise SystemExit(0)

BAD2CANON = {
    "succeeded":"done","success":"done","completed":"done","complete":"done",
    "failed":"error","failure":"error","fail":"error","cancelled":"canceled",
}
RE = re.compile(r"\b(succeeded|success|completed|complete|failed|failure|fail|cancelled)\b", re.I)

def _canon(v: str) -> str:
    s = (v or "").strip().lower()
    return BAD2CANON.get(s, s)

def _log(tag: str, detail: str):
    print(f"[status-guard] {tag}: {detail!r}", file=sys.stderr)
    print("".join(traceback.format_stack(limit=12)), file=sys.stderr)

def _touch(obj) -> bool:
    try:
        if hasattr(obj, "status"):
            tn = getattr(obj, "__tablename__", "") or getattr(getattr(obj, "__table__", None), "name", "")
            return True if not tn else (tn == "tasks")
    except Exception:
        pass
    return False

@event.listens_for(Session, "before_flush")
def _guard_flush(session, ctx, instances):
    for obj in list(session.new) + list(session.dirty):
        if not _touch(obj): continue
        try: val = getattr(obj, "status", None)
        except Exception: continue
        if not isinstance(val, str): continue
        low = val.strip().lower()
        if low in BAD2CANON:
            if MODE == "fix":
                setattr(obj, "status", _canon(val)); _log("FIXED on flush", val)
            elif MODE == "warn":
                _log("WARN on flush", val)
            else:
                _log("ERROR on flush", val); raise ValueError(f"non-canonical status: {val!r}")

@event.listens_for(Engine, "before_cursor_execute", retval=True)
def _guard_sql(conn, cursor, statement, parameters, context, executemany):
    st = (statement or "").lower()
    if not ((" update " in st or " insert " in st) and " tasks" in st and " status" in st):
        return statement, parameters
    bad = RE.search(st) is not None
    if not bad:
        try:
            items = parameters if executemany and isinstance(parameters, (list, tuple)) else [parameters]
            for row in items:
                vals = row.values() if isinstance(row, dict) else (row if isinstance(row, (list, tuple)) else [])
                for v in vals:
                    if isinstance(v, str) and v.strip().lower() in BAD2CANON:
                        bad = True; break
                if bad: break
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
                _log("FIXED in SQL", statement[:200])
            except Exception:
                _log("WARN (could-not-fix) SQL", statement[:200])
        elif MODE == "warn":
            _log("WARN in SQL", statement[:200])
        else:
            _log("ERROR in SQL", statement[:200]); raise ValueError("non-canonical status in SQL")
    return statement, parameters
PY

# 2) Ensure Dockerfiles COPY the guard and set PYTHONPATH so Python finds it
patched=0
for df in Dockerfile api/Dockerfile worker/Dockerfile services/api/Dockerfile services/worker/Dockerfile; do
  [ -f "$df" ] || continue
  grep -q 'sitecustomize.py' "$df" || {
    printf '\n# Canonical status guard\nENV PYTHONUNBUFFERED=1\nENV PYTHONPATH=/app\nCOPY sitecustomize.py /app/sitecustomize.py\n' >> "$df"
    echo "patched Dockerfile: $df"; patched=1
  }
done
[ "$patched" -eq 1 ] || echo "note: No Dockerfile patched (maybe already has sitecustomize.py COPY)."

# 3) Compose override to set STATUS_GUARD_MODE on api/worker
cat > docker-compose.override.yml <<'YAML'
services:
  api:
    environment:
      STATUS_GUARD_MODE: "error"   # use "fix" to auto-rewrite while hunting source
  worker:
    environment:
      STATUS_GUARD_MODE: "error"
YAML
echo "wrote docker-compose.override.yml (override or remove after fixing sources)."

# 4) Rebuild and restart
echo "== Building images (no cache) =="
docker compose build --no-cache api worker || docker compose build --no-cache

echo "== Restarting =="
docker compose up -d api worker || docker compose up -d

# 5) Quick verification: guard is present and mode is set
set +e
docker compose exec -T api python -c "import importlib.util;print(bool(importlib.util.find_spec('sitecustomize'))) or exit(1)"
docker compose exec -T worker python -c "import importlib.util;print(bool(importlib.util.find_spec('sitecustomize'))) or exit(1)"
docker compose exec -T worker sh -lc 'echo MODE=$STATUS_GUARD_MODE'
set -e

echo "Patch applied and services rebuilt."
echo "Now re-run your status test. If something still writes 'succeeded', the worker/API will throw with a stacktrace pointing to the exact file/line."
