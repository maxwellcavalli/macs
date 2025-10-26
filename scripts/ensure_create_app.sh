#!/usr/bin/env bash
set -euo pipefail
MAIN="app/main.py"
[ -f "$MAIN" ] || { echo "missing $MAIN"; exit 1; }

# Ensure we can import BodySizeLimitASGI safely
grep -q 'asgi_limit' "$MAIN" || sed -i '1s/^/from .asgi_limit import BodySizeLimitASGI\n/' "$MAIN"
grep -q 'BodySizeLimitASGI' "$MAIN" || sed -i '1s/^/from .asgi_limit import BodySizeLimitASGI\n/' "$MAIN"

# Add create_app() if not present
if ! grep -q '^def create_app' "$MAIN"; then
  cat >> "$MAIN" <<'PY'

def create_app():
    """
    Uvicorn factory entrypoint that returns the app wrapped by the size limiter.
    Returns an ASGI callable. Safe if limiter import fails.
    """
    try:
        wrapped = BodySizeLimitASGI(app)
    except Exception:
        wrapped = app
    return wrapped
PY
  echo "create_app added to $MAIN"
else
  echo "create_app already present in $MAIN"
fi
