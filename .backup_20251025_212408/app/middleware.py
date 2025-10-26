from __future__ import annotations
import uuid, time, logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from .logctx import set_request_id, set_route
from .logging_setup import get_logger

log = get_logger("http")

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        set_request_id(rid)
        set_route(f"{request.method} {request.url.path}")
        t0 = time.time()
        try:
            resp: Response = await call_next(request)
            ms = int((time.time()-t0)*1000)
            log.info("request.ok", {"status": resp.status_code, "duration_ms": ms})
            resp.headers["X-Request-ID"] = rid
            return resp
        except Exception as e:
            ms = int((time.time()-t0)*1000)
            log.error(f"request.err: {e}", {"duration_ms": ms})
            raise
