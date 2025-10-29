#!/usr/bin/env bash
set -Eeuo pipefail

python3 - <<'PY'
import io, os, re, sys, pathlib
p = pathlib.Path("app/middleware_canon.py")
src = p.read_text(encoding="utf-8")

# Replace the whole SSECanonicalizerMiddleware class safely
new_sse = r'''
class SSECanonicalizerMiddleware:
    """
    For text/event-stream, rewrite only the JSON after 'data:' and preserve SSE framing.
    - We buffer by double-newline (\n\n), which is the SSE event boundary.
    - We keep [DONE] untouched.
    - We add Cache-Control: no-cache and X-Accel-Buffering: no to discourage proxy buffering.
    - Set env SSE_CANON_MODE=off to bypass this middleware for A/B testing.
    """
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        import os, json
        mode = (os.getenv("SSE_CANON_MODE","on") or "on").lower()
        if mode in ("off","0","false","disabled"):
            await self.app(scope, receive, send)
            return

        is_sse = {"value": False}
        buf = {"pending": ""}

        def _h2d(headers):
            d = {}
            for k,v in headers:
                d[k.decode().lower()] = v.decode()
            return d
        def _d2h(d):
            return [(k.encode(), v.encode()) for k,v in d.items()]

        async def send_wrapper(event):
            if event["type"] == "http.response.start":
                headers = event.get("headers", [])
                hd = _h2d(headers)
                ct = (hd.get("content-type") or "").lower()
                is_sse["value"] = "text/event-stream" in ct
                if is_sse["value"]:
                    hd.setdefault("cache-control","no-cache")
                    hd.setdefault("x-accel-buffering","no")
                    e = dict(event)
                    e["headers"] = _d2h(hd)
                    await send(e)
                    return
                await send(event)
                return

            if event["type"] == "http.response.body" and is_sse["value"]:
                chunk = event.get("body", b"").decode("utf-8", "ignore")
                more = bool(event.get("more_body", False))
                buf["pending"] += chunk

                # split on SSE event boundary
                parts = buf["pending"].split("\n\n")
                if more:
                    buf["pending"] = parts.pop()  # keep last incomplete event
                else:
                    buf["pending"] = ""           # flush all if final

                out = []
                for ev in parts:
                    # ev has no trailing \n\n now. Re-add later.
                    if ev.startswith("data:"):
                        payload = ev[5:].lstrip()
                        if payload == "[DONE]":
                            out.append("data: [DONE]\n\n")
                        else:
                            try:
                                obj = json.loads(payload)
                                try:
                                    from .status_norm import norm_payload
                                except Exception:
                                    def norm_payload(x): return x
                                obj = norm_payload(obj)
                                out.append("data: " + json.dumps(obj, ensure_ascii=False) + "\n\n")
                            except Exception:
                                # not JSON — leave untouched
                                out.append(ev + "\n\n")
                    else:
                        # comments or other fields — pass through
                        out.append(ev + "\n\n")

                data = "".join(out).encode("utf-8")
                await send({"type":"http.response.body","body": data, "more_body": more})
                return

            await send(event)

        await self.app(scope, receive, send_wrapper)
PY

echo "Patched SSE middleware."
