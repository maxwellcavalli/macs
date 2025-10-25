#!/usr/bin/env bash
set -euo pipefail

main="app/main.py"
mod="app/otel_inline.py"
ts="$(date +%s)"

[ -f "$main" ] || { echo "missing $main"; exit 1; }

# 1) Write (or refresh) otel_inline.py
mkdir -p app
cat > "$mod" <<'PY'
import os, secrets
from typing import Any
from starlette.middleware.base import BaseHTTPMiddleware

def _truthy(v: str) -> bool:
    return str(v).lower() in ("1","true","yes","on")

class _TraceHeaderMW(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # run request
        response = await call_next(request)
        # try to get OTel trace id; fallback to random
        trace_hex = None
        try:
            from opentelemetry import trace  # type: ignore
            span = trace.get_current_span()
            ctx = span.get_span_context() if span else None
            if ctx and ctx.is_valid:
                trace_hex = f"{ctx.trace_id:032x}"
        except Exception:
            trace_hex = None
        if not trace_hex:
            trace_hex = secrets.token_hex(16)
        response.headers["x-trace-id"] = trace_hex
        if getattr(request.app.state, "otel_enabled", False) or _truthy(os.getenv("MACS_OTEL_ENABLED","1")):
            response.headers["x-otel-enabled"] = "1"
        return response

def enable_otel_headers(app: Any) -> bool:
    """Enable OTel (if libs present) and always attach trace-id/otel headers."""
    enabled = _truthy(os.getenv("MACS_OTEL_ENABLED", "1"))
    setattr(app.state, "otel_enabled", enabled)

    # attach header middleware once
    names = [getattr(getattr(m,"cls",m), "__name__", str(m)) for m in getattr(app, "user_middleware", [])]
    if "_TraceHeaderMW" not in names and "InlineTraceHeaderMiddleware" not in names and "TraceHeaderMiddleware" not in names:
        app.add_middleware(_TraceHeaderMW)

    # try to init OTel + ASGI middleware (optional)
    if enabled:
        try:
            from opentelemetry import trace  # type: ignore
            from opentelemetry.sdk.resources import Resource  # type: ignore
            from opentelemetry.sdk.trace import TracerProvider  # type: ignore
            from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter  # type: ignore
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor  # type: ignore
            from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware  # type: ignore
            service = os.getenv("OTEL_SERVICE_NAME", "macs-api")
            provider = TracerProvider(resource=Resource.create({"service.name": service}))
            # console exporter by default (keeps things local/dev)
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
            trace.set_tracer_provider(provider)
            # instrument app and add ASGI middleware if missing
            FastAPIInstrumentor.instrument_app(app)
            names = [getattr(getattr(m,"cls",m), "__name__", str(m)) for m in getattr(app, "user_middleware", [])]
            if "OpenTelemetryMiddleware" not in names:
                app.add_middleware(OpenTelemetryMiddleware)
        except Exception:
            pass
    return enabled
PY

# 2) Patch main.py — add import + call after app = FastAPI(...)
cp -n "$main" "$main.bak.$ts" || true

if ! grep -q "INLINE_OTEL_PATCH_v1" "$main"; then
  awk '
    BEGIN{ did_import=0; did_call=0 }
    # after the FastAPI import, add our import (once)
    /^from[[:space:]]+fastapi[[:space:]]+import[[:space:]]+FastAPI/ && did_import==0 {
      print $0
      print "from .otel_inline import enable_otel_headers  # INLINE_OTEL_PATCH_v1"
      did_import=1
      next
    }
    # after the first app = FastAPI(…) line, call our enabler (once)
    did_call==0 && $0 ~ /app[[:space:]]*=[[:space:]]*FastAPI[[:space:]]*\(/ {
      print $0
      print "enable_otel_headers(app)  # INLINE_OTEL_PATCH_v1"
      did_call=1
      next
    }
    { print $0 }
  ' "$main" > "$main.tmp.$ts"

  mv "$main.tmp.$ts" "$main"
  echo "patched $main (import+call inserted). backup: $main.bak.$ts"
else
  echo "$main already contains INLINE_OTEL_PATCH_v1 — skipping"
fi

echo "done."
