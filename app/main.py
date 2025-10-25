from __future__ import annotations
from fastapi import FastAPI
from .sse_early_exit_mw import SSEEarlyExitMiddleware
from fastapi.middleware.cors import CORSMiddleware
from .api import router, hub
from .queue import JobQueue
from .logging_setup import setup_json_logging, get_logger
from .middleware import RequestIDMiddleware

setup_json_logging()
log = get_logger("bootstrap")

app = FastAPI(title="MACS API")



# Early-exit SSE when artifacts already exist
app.add_middleware(SSEEarlyExitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)
app.add_middleware(RequestIDMiddleware)

app.include_router(router)

@app.on_event("startup")
async def _startup():
    # create and start the queue
    jobq = JobQueue(hub)
    await jobq.start()
    # expose via app.state (authoritative)
    app.state.job_queue = jobq
    # also set module global for older call sites
    from . import api as api_module
    api_module.job_queue = jobq
    log.info("startup complete")

@app.get("/")
async def root():
    return {"ok": True, "service": "macs-api"}
