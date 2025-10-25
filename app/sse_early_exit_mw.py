from typing import Callable, Awaitable, Dict, Any, Iterable
import os, json, pathlib, urllib.parse, re

def _flag(name: str, default: str = "1") -> bool:
    return (os.environ.get(name, default) or "").strip() not in ("0", "false", "False", "")

def _csv(name: str, default: str) -> list[str]:
    raw = os.environ.get(name, default)
    return [s.strip() for s in raw.split(",") if s.strip()]

ENABLED                  = _flag("SSE_EARLY_EXIT_ENABLED", "1")
DIAGNOSTIC_HEADER        = _flag("SSE_EARLY_EXIT_DIAGNOSTIC", "0")
ACCEPT_ONLY              = _flag("SSE_EARLY_EXIT_ACCEPT_ONLY", "0")
PATH_HINTS               = _csv("SSE_EARLY_EXIT_PATH_HINTS", "stream,events")
REQUIRE_ID               = _flag("SSE_EARLY_EXIT_REQUIRE_ID", "1")
ARTIFACTS_DIR            = os.environ.get("ARTIFACTS_DIR")

def _fallback_resolve_root(task_id: str) -> str:
    base = ARTIFACTS_DIR
    candidates = ([base] if base else []) + [
        "./artifacts", "/data/artifacts", "/app/artifacts", "/workspace/artifacts", "/srv/artifacts"
    ]
    for c in candidates:
        if not c:
            continue
        p = pathlib.Path(c)
        try:
            p.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        if p.exists():
            return str(p / task_id)
    return str(pathlib.Path("./artifacts") / task_id)

try:
    from app.artifacts import _resolve_root as _project_resolve_root  # type: ignore
except Exception:
    _project_resolve_root = None

def _resolve_root(task_id: str) -> str:
    if _project_resolve_root:
        try:
            return _project_resolve_root(task_id)
        except Exception:
            pass
    return _fallback_resolve_root(task_id)

UUID_LIKE = re.compile(r'^[0-9a-fA-F-]{16,64}$')

def _extract_task_id(path: str, query: bytes) -> str | None:
    if query:
        q = urllib.parse.parse_qs(query.decode("utf-8"), keep_blank_values=True)
        for key in ("task_id", "id", "task"):
            if key in q and q[key] and q[key][0]:
                return q[key][0]
    segs = [s for s in path.split("/") if s]
    if not segs:
        return None
    for marker in PATH_HINTS:
        if marker in segs:
            i = segs.index(marker)
            if i - 1 >= 0 and UUID_LIKE.match(segs[i-1] or ""):
                return segs[i-1]
            if i + 1 < len(segs) and UUID_LIKE.match(segs[i+1] or ""):
                return segs[i+1]
            if i - 1 >= 0:
                return segs[i-1]
            if i + 1 < len(segs):
                return segs[i+1]
    if "tasks" in segs:
        i = segs.index("tasks")
        if i + 1 < len(segs):
            cand = segs[i+1]
            if cand and cand not in PATH_HINTS:
                return cand
    if UUID_LIKE.match(segs[-1] or ""):
        return segs[-1]
    return None

def _headers_dict(scope: Dict[str, Any]) -> Dict[bytes, bytes]:
    h = {}
    for k, v in (scope.get("headers") or []):
        h[k] = v
    return h

def _wants_sse(scope: Dict[str, Any]) -> bool:
    path = scope.get("path", "") or ""
    headers = {k.lower(): v for k, v in _headers_dict(scope).items()}
    accept = headers.get(b"accept", b"")
    if ACCEPT_ONLY:
        return b"text/event-stream" in accept
    if any(h in path for h in PATH_HINTS):
        return True
    return b"text/event-stream" in accept

class SSEEarlyExitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope: Dict[str, Any], receive: Callable[[], Awaitable[Dict[str, Any]]], send: Callable[[Dict[str, Any]], Awaitable[None]]) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        # diagnostic header passthrough wrapper
        async def send_with_diag(message: Dict[str, Any]) -> None:
            if DIAGNOSTIC_HEADER and message.get("type") == "http.response.start":
                headers: list[tuple[bytes, bytes]] = list(message.get("headers") or [])
                headers.append((b"x-sse-early-exit", b"enabled"))
                message = {**message, "headers": headers}
            await send(message)

        if not ENABLED:
            await self.app(scope, receive, send_with_diag)
            return

        path = scope.get("path", "") or ""
        query = scope.get("query_string") or b""

        if _wants_sse(scope):
            task_id = _extract_task_id(path, query)
            if not task_id and not REQUIRE_ID:
                # if explicitly allowed, try default dir (rare)
                task_id = "unknown"
            if task_id:
                try:
                    root = _resolve_root(task_id)
                    if root and os.path.isdir(root):
                        payload = (json.dumps({"status": "done", "note": "artifacts-present"}) + "\n").encode("utf-8")
                        headers: Iterable[tuple[bytes, bytes]] = [
                            (b"content-type", b"text/event-stream"),
                            (b"cache-control", b"no-cache"),
                            (b"connection", b"keep-alive"),
                        ]
                        if DIAGNOSTIC_HEADER:
                            headers.append((b"x-sse-early-exit", b"enabled"))
                        await send({"type": "http.response.start", "status": 200, "headers": headers})
                        await send({"type": "http.response.body", "body": payload, "more_body": False})
                        return
                except Exception:
                    pass

        await self.app(scope, receive, send_with_diag)
