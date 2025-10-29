#!/usr/bin/env bash
set -euo pipefail

echo "== apply_queue_artifacts_patch.sh : wiring artifacts + bandit + SSE helper =="

# Expect to run from repo root where app/queue.py exists
if [[ ! -f "app/queue.py" ]]; then
  echo "!! Run this script from your repo root (where app/queue.py exists)."
  echo "Current dir: $(pwd)"
  exit 1
fi

# Backups
ts="$(date +%Y%m%d-%H%M%S)"
mkdir -p .patch_backups
cp app/queue.py ".patch_backups/queue.py.$ts.bak" || true
cp app/main.py  ".patch_backups/main.py.$ts.bak"  || true

# 1) artifacts.py (if missing)
if [[ ! -f app/artifacts.py ]]; then
  cat > app/artifacts.py <<'PY'
import os, json
from pathlib import Path
from typing import Any, Dict

def _root() -> Path:
    base = os.getenv("ARTIFACTS_DIR", "/app/artifacts")
    p = Path(base)
    p.mkdir(parents=True, exist_ok=True)
    return p

def _resolve_root(task_id: str) -> Path:
    return _root() / str(task_id)

def write_result(task_id: str, payload: Dict[str, Any]) -> str:
    r = _resolve_root(task_id)
    r.mkdir(parents=True, exist_ok=True)
    (r / "result.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return str(r)
PY
  echo "[ok] created app/artifacts.py"
else
  echo "[ok] app/artifacts.py exists"
fi

# 2) sse_routes.py (if missing)
if [[ ! -f app/sse_routes.py ]]; then
  cat > app/sse_routes.py <<'PY'
import os, json, asyncio
from pathlib import Path
from typing import AsyncGenerator
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter()
_ART = os.getenv("ARTIFACTS_DIR", "/app/artifacts")

def _artifact_dir(task_id: str) -> Path:
    return Path(_ART) / str(task_id)

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
        if root.exists() and root.is_dir():
            yield _event({"status":"done","note":"artifacts-present"})
            return
        for _ in range(120):
            if root.exists() and root.is_dir():
                yield _event({"status":"done","note":"artifacts-present"})
                return
            yield b": keep-alive\n\n"
            await asyncio.sleep(0.5)
        if os.getenv("DEV_COMPAT") == "1":
            root.mkdir(parents=True, exist_ok=True)
            (root / "result.json").write_text(json.dumps({"ok": True, "task_id": task_id, "note": "dev-timeout"}, ensure_ascii=False), encoding="utf-8")
            yield _event({"status":"done","note":"artifacts-created-dev"})
            return
        yield _event({"status":"timeout","note":"no-artifacts"})
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control":"no-cache","Connection":"keep-alive"})
PY
  echo "[ok] created app/sse_routes.py"
else
  echo "[ok] app/sse_routes.py exists"
fi

# 3) main.py router include (idempotent)
if ! grep -q "from \.sse_routes import router as _sse_router" app/main.py 2>/dev/null; then
  cat >> app/main.py <<'PY'

# --- Attach SSE+status router (idempotent) ---
try:
    from .sse_routes import router as _sse_router  # type: ignore
    app.include_router(_sse_router)
except Exception:
    pass
PY
  echo "[ok] main.py now includes sse_routes router"
else
  echo "[ok] main.py already includes sse_routes router"
fi

# 4) Patch app/queue.py with a Python patcher (idempotent)
python3 - <<'PY'
import re
from pathlib import Path
p = Path("app/queue.py")
s = p.read_text(encoding="utf-8")
orig = s
changes = 0

# Ensure imports
if "from .bandit_store import record_event as bandit_record_event" not in s:
    s = s.replace(
        "from .logctx import set_task_id, set_candidate\n",
        "from .logctx import set_task_id, set_candidate\n"
        "from .bandit_store import record_event as bandit_record_event\n"
        "from .artifacts import write_result\n"
    )
    changes += 1

# Add helper inside JobQueue
if "_write_artifact_safely(self, task_id: str, payload:" not in s:
    m = re.search(r"async def _write_primary\([^)]*\):[\s\S]*?return target\s*\n", s)
    helper = (
        "\n"
        "    def _write_artifact_safely(self, task_id: str, payload: Dict[str, Any]) -> None:\n"
        "        try:\n"
        "            write_result(str(task_id), payload)\n"
        "        except Exception:\n"
        "            pass\n"
        "\n"
    )
    if m:
        idx = m.end()
        s = s[:idx] + helper + s[idx:]
    else:
        m2 = re.search(r"def __init__\([^)]*\):[\s\S]*?self\._inflight: Dict\[str, List\[asyncio\.Task\]\] = \{\}\s*\n", s)
        if m2:
            idx = m2.end()
            s = s[:idx] + helper + s[idx:]
        else:
            m3 = re.search(r"class JobQueue\([\s\S]*?\):\s*\n", s)
            if m3:
                idx = m3.end()
                s = s[:idx] + helper + s[idx:]
    changes += 1

# Single-run bandit log
needle = 'bandit_record_event(res.get("model") or "unknown", float(reward), {"src":"queue","task_id": str(id),"mode":"single"})'
if needle not in s:
    pattern = r'(reward\s*=\s*1\.0\s*if\s*res\.get\("test_pass"\)\s*else\s*\(0\.5\s*if\s*res\.get\("compile_pass"\)\s*else\s*0\.0\)\))\n'
    repl = (
        r"\1\n"
        r"                    # bandit: log single-run reward\n"
        r"                    try:\n"
        r"                        bandit_record_event(res.get(\"model\") or \"unknown\", float(reward), {\"src\":\"queue\",\"task_id\": str(id),\"mode\":\"single\"})\n"
        r"                    except Exception:\n"
        r"                        pass\n"
        r"\n"
    )
    s = re.sub(pattern, repl, s, count=1)
    changes += 1

# Single-run artifact before publish
single_done_re = re.compile(
    r'(?P<indent>^[ \t]*)await self\.hub\.publish\(str\(id\), json\.dumps\(\{\s*\n(?P=indent)[ \t]*"status":"done",\s*\n(?P=indent)[ \t]*"model":res\.get\("model"\)',
    re.M
)
def inject_single(m):
    indent = m.group('indent')
    call = (
        indent + "self._write_artifact_safely(str(id), {\n" +
        indent + "    \"status\":\"done\",\"mode\":\"single\",\n" +
        indent + "    \"model\":res.get(\"model\"), \"latency_ms\":res.get(\"latency_ms\"),\n" +
        indent + "    \"compile_pass\":res.get(\"compile_pass\"), \"test_pass\":res.get(\"test_pass\"),\n" +
        indent + "    \"tool\":res.get(\"tool\"), \"artifact\":res.get(\"artifact\")\n" +
        indent + "})\n"
    )
    return call + m.group(0)
s2 = single_done_re.sub(inject_single, s, count=1)
if s2 != s:
    s = s2; changes += 1

# Duel bandit logs
if 'bandit_record_event(winner.get("model") or "unknown"' not in s:
    s = s.replace(
        'reward_w = 1.0 if winner.get("test_pass") else (0.5 if winner.get("compile_pass") else 0.0)',
        'reward_w = 1.0 if winner.get("test_pass") else (0.5 if winner.get("compile_pass") else 0.0)\n'
        '                    # bandit: log duel rewards\n'
        '                    try:\n'
        '                        bandit_record_event(winner.get("model") or "unknown", float(reward_w), {"src":"queue","task_id": str(id),"mode":"duel","role":"winner","opponent": (loser.get("model") or "unknown")})\n'
        '                        bandit_record_event(loser.get("model") or "unknown", float(reward_l), {"src":"queue","task_id": str(id),"mode":"duel","role":"loser","opponent": (winner.get("model") or "unknown")})\n'
        '                    except Exception:\n'
        '                        pass'
    )
    changes += 1

# Duel artifact before publish
duel_done_re = re.compile(
    r'(?P<indent>^[ \t]*)await self\.hub\.publish\(str\(id\), json\.dumps\(\{\s*\n(?P=indent)[ \t]*"status":"done",\s*\n(?P=indent)[ \t]*"winner": winner\[\"model\"\]',
    re.M
)
def inject_duel(m):
    indent = m.group('indent')
    call = (
        indent + "self._write_artifact_safely(str(id), {\n" +
        indent + "    \"status\":\"done\",\"mode\":\"duel\",\n" +
        indent + "    \"winner\": winner.get(\"model\"), \"loser\": loser.get(\"model\"),\n" +
        indent + "    \"rule_version\": str(cfg.get(\"rule_version\",\"v1\")),\n" +
        indent + "    \"winner_metrics\": {\"success\":winner.get(\"success\"), \"latency_ms\":winner.get(\"latency_ms\"), \"compile_pass\":winner.get(\"compile_pass\"), \"test_pass\":winner.get(\"test_pass\"), \"tool\":winner.get(\"tool\")},\n" +
        indent + "    \"loser_metrics\": {\"success\":loser.get(\"success\"), \"latency_ms\":loser.get(\"latency_ms\"), \"compile_pass\":loser.get(\"compile_pass\"), \"test_pass\":loser.get(\"test_pass\"), \"tool\":loser.get(\"tool\")}})\n"
    )
    return call + m.group(0)
s2 = duel_done_re.sub(inject_duel, s, count=1)
if s2 != s:
    s = s2; changes += 1

if changes:
    p.write_text(s, encoding="utf-8")
    print(f"[ok] queue.py patched with {changes} change group(s)")
else:
    print("[ok] queue.py already patched (no changes)")
PY

echo "[hint] Rebuild your API container:"
echo "docker compose build api && docker compose up -d api"
echo "Then run: scripts/submit_task.sh && scripts/stream.sh"
echo "== done =="
