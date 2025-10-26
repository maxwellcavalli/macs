#!/usr/bin/env bash
set -euo pipefail
CID="$(docker compose ps -q api)"
docker exec "$CID" sh -lc 'python3 - <<PY
from app.main import app
print([getattr(getattr(m,"cls",m),"__name__",str(m)) for m in app.user_middleware])
PY'
