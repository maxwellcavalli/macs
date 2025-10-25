#!/usr/bin/env bash
set -euxo pipefail
SVC="${SVC:-api}"
CID="$(docker compose ps -q "$SVC")"

echo "==> Env inside container"
docker exec "$CID" sh -lc 'echo MACS_OTEL_ENABLED=$MACS_OTEL_ENABLED; echo MACS_OTEL_EXPORTER=$MACS_OTEL_EXPORTER; echo OTEL_SERVICE_NAME=$OTEL_SERVICE_NAME'

echo "==> Python check: main imports + middleware presence"
docker exec "$CID" sh -lc 'python3 - <<PY
import importlib, json
ok = {}
try:
  m = importlib.import_module("app.main")
  ok["import_main"]=True
  app = getattr(m,"app",None)
  ok["has_app"]=bool(app)
  if app:
    mids=[getattr(getattr(x,"cls",x), "__name__", str(x)) for x in getattr(app, "user_middleware", [])]
    ok["middleware"]=mids
    ok["otel_enabled"]=bool(getattr(app.state,"otel_enabled", False))
except Exception as e:
  ok["error"]=repr(e)
print(json.dumps(ok, indent=2))
PY'

echo "==> Recent logs (10s)"
docker logs "$CID" --since 10s | tail -n 200 || true
