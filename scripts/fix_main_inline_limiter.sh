#!/usr/bin/env bash
set -euo pipefail
MAIN="app/main.py"
TS=$(date +%s)
[ -f "$MAIN" ] || { echo "missing $MAIN"; exit 1; }
cp -p "$MAIN" "$MAIN.bak.$TS"

python3 - <<'PY'
import re, pathlib
p = pathlib.Path("app/main.py")
s = p.read_text(encoding="utf-8")

# 1) Keep any __future__ imports at the very top
lines = s.splitlines()
futures = [ln for ln in lines if ln.strip().startswith("from __future__ import")]
if futures:
    body = "\n".join(ln for ln in lines if ln.strip() not in set(futures))
    s = "\n".join(futures) + "\n\n" + body

# 2) Remove any external limiter import / premature wrapping
s = re.sub(r'^\s*from\s+\.\s*asgi_limit\s+import\s+BodySizeLimitASGI\s*\n', '', s, flags=re.M)
s = re.sub(r'^\s*app\s*=\s*BodySizeLimitASGI\(app\)\s*\n', '', s, flags=re.M)

# 3) Insert an inline ASGI limiter class if not present
if "class BodySizeLimitASGI" not in s:
    limiter = '''
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
'''.strip("\n")
    parts = s.splitlines()
    # insert right after last __future__ import (or at top if none)
    insert_at = 0
    for i, ln in enumerate(parts):
        if ln.strip().startswith("from __future__ import"):
            insert_at = i + 1
    parts.insert(insert_at, limiter + "\n")
    s = "\n".join(parts)

# 4) Ensure a factory exists that returns the wrapped app
if not re.search(r'^\s*def\s+create_app\s*\(', s, flags=re.M):
    s += '''

def create_app():
    """Uvicorn --factory entrypoint: returns app wrapped by BodySizeLimitASGI."""
    try:
        return BodySizeLimitASGI(app)
    except Exception:
        return app
'''
p.write_text(s, encoding="utf-8")
print("ok")
PY

echo "Patched $MAIN (backup: $MAIN.bak.$TS)"
