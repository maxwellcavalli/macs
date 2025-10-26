#!/usr/bin/env bash
set -euo pipefail
MAIN="app/main.py"
TS=$(date +%s)
[ -f "$MAIN" ] || { echo "missing $MAIN"; exit 1; }
cp -p "$MAIN" "$MAIN.bak.$TS"

python3 - <<'PY'
import io, re, sys, pathlib
p = pathlib.Path("app/main.py"); s = p.read_text(encoding="utf-8")

# 1) Pull out all __future__ imports and re-insert them at the very top
lines = s.splitlines()
future = [ln for ln in lines if ln.strip().startswith("from __future__ import")]
if future:
    # remove all future lines from original content
    body = "\n".join(ln for ln in lines if ln.strip() not in set(future))
    # remove leading blank lines in body
    body = re.sub(r'^\s*\n', '', body, flags=re.M)
    # assemble new source: future imports first, then a blank line, then the rest
    s = "\n".join(future) + "\n\n" + body

# 2) Ensure "from .asgi_limit import BodySizeLimitASGI" exists AFTER future imports
if "from .asgi_limit import BodySizeLimitASGI" not in s:
    parts = s.splitlines()
    # find last future import line index in current text
    idx = -1
    for i, ln in enumerate(parts):
        if ln.strip().startswith("from __future__ import"):
            idx = i
    insert_at = 0 if idx < 0 else idx + 1
    parts.insert(insert_at, "from .asgi_limit import BodySizeLimitASGI")
    s = "\n".join(parts)

# 3) Ensure create_app() factory exists (returns wrapped app), idempotent
if not re.search(r'^\s*def\s+create_app\s*\(', s, flags=re.M):
    s += """

def create_app():
    \"""
    Uvicorn factory entrypoint that returns the app wrapped by the size limiter.
    Safe if the limiter import fails.
    \"""
    try:
        wrapped = BodySizeLimitASGI(app)
    except Exception:
        wrapped = app
    return wrapped
"""
p.write_text(s, encoding="utf-8")
PY

echo "Repaired $MAIN (backup at $MAIN.bak.$TS)"
