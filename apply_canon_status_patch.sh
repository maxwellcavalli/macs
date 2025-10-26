#!/usr/bin/env bash
set -Eeuo pipefail

mkdir -p app

# ---------- app/status_norm.py ----------
cat > app/status_norm.py <<'PY'
from typing import Any, Mapping

CANON = {"queued","running","done","error","canceled"}
MAP = {
    "succeeded":"done", "success":"done", "completed":"done", "complete":"done",
    "failed":"error", "failure":"error", "fail":"error",
    "cancelled":"canceled",
}

def norm_status(s: Any) -> Any:
    if s is None: return s
    v = str(getattr(s, "value", s)).strip().lower()
    return MAP.get(v, v)

def norm_payload(obj: Any) -> Any:
    # Recursively rewrite {"status": "..."} anywhere in the object
    if isinstance(obj, Mapping):
        d = dict(obj)
        if "status" in d:
            d["status"] = norm_status(d["status"])
        for k, v in list(d.items()):
            d[k] = norm_payload(v)
        return d
    if isinstance(obj, list):
        return [norm_payload(x) for x in obj]
    return obj
PY

# ---------- app/middleware_canon.py ----------
cat > app/middleware_canon.py <<'PY'
import json
from typing import Dict, Tuple, List
from starlette.types import ASGIApp, Receive, Scope, Send
from .status_norm import norm_payload

def _headers_to_dict(raw: List[Tuple[bytes, bytes]]) -> Dict[str, str]:
    d: Dict[str, str] = {}
    for k, v in raw:
        d[k.decode().lower()] = v.decode()
    return d

def _dict_to_headers(d: Dict[str, str]) -> List[Tuple[bytes, bytes]]:
    return [(k.encode(), v.encode()) for k, v in d.items()]

class JSONCanonicalizerMiddleware:
    """
    For application/json responses, buffer the body, canonicalize any 'status' fields,
    and emit the modified JSON (drops Content-Length to avoid mismatch).
    """
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = {"defer": False, "status": 200, "headers": []}
        body_chunks: List[bytes] = []

        async def send_wrapper(event):
            if event["type"] == "http.response.start":
                headers = event.get("headers", [])
                hd = _headers_to_dict(headers)
                ct = hd.get("content-type", "").lower()
                if "application/json" in ct:
                    # defer start until we rewrite the body
                    started["defer"] = True
                    started["status"] = event["status"]
                    started["headers"] = headers
                    return
                # passthrough for non-JSON
                await send(event)
                return

            if event["type"] == "http.response.body" and started["defer"]:
                body_chunks.append(event.get("body", b""))
                if event.get("more_body", False):
                    return  # keep buffering
                # finalize
                raw = b"".join(body_chunks)
                try:
                    data = json.loads(raw.decode("utf-8"))
                    data = norm_payload(data)
                    new_body = json.dumps(data, ensure_ascii=False).encode("utf-8")
                except Exception:
                    new_body = raw  # fall back

                # send start (drop content-length so server can chunk)
                hd = _headers_to_dict(started["headers"])
                hd.pop("content-length", None)
                await send({
                    "type": "http.response.start",
                    "status": started["status"],
                    "headers": _dict_to_headers(hd),
                })
                await send({
                    "type": "http.response.body",
                    "body": new_body,
                    "more_body": False,
                })
                return

            # default passthrough
            await send(event)

        await self.app(scope, receive, send_wrapper)

class SSECanonicalizerMiddleware:
    """
    For text/event-stream, rewrite each 'data: <json>' line by canonicalizing any 'status'.
    Streaming-safe: buffers partial lines between chunks.
    """
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        is_sse = {"value": False}
        buf = {"text": ""}

        async def send_wrapper(event):
            if event["type"] == "http.response.start":
                headers = event.get("headers", [])
                hd = _headers_to_dict(headers)
                ct = hd.get("content-type", "").lower()
                is_sse["value"] = "text/event-stream" in ct
                await send(event)
                return

            if event["type"] == "http.response.body" and is_sse["value"]:
                chunk = event.get("body", b"").decode("utf-8", "ignore")
                more = event.get("more_body", False)
                buf["text"] += chunk

                out_lines: List[str] = []
                lines = buf["text"].split("\n")
                if more:
                    buf["text"] = lines.pop()  # keep last partial line
                else:
                    buf["text"] = ""           # flush all on final

                for line in lines:
                    if line.startswith("data:"):
                        payload = line[5:].strip()
                        if payload and payload != "[DONE]":
                            try:
                                obj = json.loads(payload)
                                obj = norm_payload(obj)
                                line = "data: " + json.dumps(obj, ensure_ascii=False)
                            except Exception:
                                # keep original if not JSON
                                pass
                    out_lines.append(line)

                new_body = ("\n".join(out_lines)).encode("utf-8")
                await send({"type": "http.response.body", "body": new_body, "more_body": more})
                return

            await send(event)

        await self.app(scope, receive, send_wrapper)
PY

# ---------- wire into app/main.py (idempotent) ----------
if ! grep -q "Canonical status middlewares" app/main.py 2>/dev/null; then
  cat >> app/main.py <<'PY'

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
PY
fi

echo "Patch applied. Now restart or rebuild your API service."
