from __future__ import annotations
from fastapi import APIRouter
from starlette.routing import Route
from app.main import app
from app.routers.tasks_create_fix import create_task

# Build fixed POST /v1/tasks route
tmp = APIRouter()
tmp.add_api_route("/v1/tasks", create_task, methods=["POST"])
fixed = tmp.routes[0]

# Remove any existing POST /v1/tasks routes
keep = []
for r in app.router.routes:
    if isinstance(r, Route) and getattr(r, "path", None) == "/v1/tasks" and "POST" in (r.methods or set()):
        continue
    keep.append(r)

# Prepend ours so it matches first
app.router.routes = [fixed] + keep

# Print head of routes for sanity
try:
    from datetime import datetime
    head = []
    for r in app.router.routes[:8]:
        head.append({"path": getattr(r,"path",None), "methods": sorted(list(getattr(r,"methods",[]) or []))})
    print({"ts": datetime.utcnow().isoformat()+"Z", "routes_head": head}, flush=True)
except Exception:
    pass
