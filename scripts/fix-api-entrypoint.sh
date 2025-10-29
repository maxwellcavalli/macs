#!/usr/bin/env sh
set -e

# 0) Backup
mkdir -p .backup_$(date +%Y%m%d_%H%M%S)
cp -a app/main.py .backup_*/ 2>/dev/null || true

# 1) Create a clean ASGI wrapper that includes our router
mkdir -p app
cat > app/asgi.py <<'PY'
from __future__ import annotations

# Import the existing FastAPI app object
from app.main import app

# Attach the fixed create-task router
from app.routers.tasks_create_fix import router as tasks_create_fix_router
app.include_router(tasks_create_fix_router)
PY

# 2) Make sure we didn't leave any stray router imports inside main.py
#    (these could trip the __future__ rule again)
if grep -q "tasks_create_fix_router" app/main.py 2>/dev/null; then
  # Remove the import line and include_router line safely
  sed -i -E '/tasks_create_fix_router/d' app/main.py
fi

# 3) Ensure the router file exists (no-op if you already created it earlier)
if [ ! -f app/routers/tasks_create_fix.py ]; then
  mkdir -p app/routers
  cat > app/routers/tasks_create_fix.py <<'PY'
from __future__ import annotations
import os, uuid, json
from typing import Literal, Optional, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

DBURL = os.environ.get("DATABASE_URL", "")
if DBURL.startswith("postgresql://"):
    DBURL = DBURL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(DBURL, pool_size=5, max_overflow=5)
router = APIRouter()

class TaskInput(BaseModel):
    goal: str = Field(..., min_length=1)
    language: str = "python"
    repo: Dict[str, Any] = Field(default_factory=dict)
    constraints: Dict[str, Any] = Field(default_factory=dict)
    model: str = "qwen2.5-coder:7b-instruct-q4_K_M"
    options: Dict[str, Any] = Field(default_factory=dict)

class TaskCreate(BaseModel):
    type: Literal["CODE","PLAN","REFACTOR","TEST","DOC"]
    input: TaskInput
    metadata: Dict[str, Any] = Field(default_factory=dict)
    template_ver: Optional[int] = None

@router.post("/v1/tasks")
async def create_task(body: TaskCreate):
    tid = str(uuid.uuid4())
    metadata = dict(body.metadata or {})
    metadata.setdefault("input", body.input.model_dump())

    sql = text("""
        INSERT INTO public.tasks
            (id, type, status, goal, language, model, options, repo, constraints, metadata, template_ver)
        VALUES
            (:id, :type, 'queued', :goal, :language, :model,
             CAST(:options AS JSONB), CAST(:repo AS JSONB), CAST(:constraints AS JSONB),
             CAST(:metadata AS JSONB), :template_ver)
    """)

    params = {
        "id": tid,
        "type": body.type,
        "goal": body.input.goal.strip(),
        "language": body.input.language,
        "model": body.input.model,
        "options": json.dumps(body.input.options),
        "repo": json.dumps(body.input.repo),
        "constraints": json.dumps(body.input.constraints),
        "metadata": json.dumps(metadata),
        "template_ver": body.template_ver,
    }

    try:
        async with engine.begin() as conn:
            await conn.execute(sql, params)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB insert failed: {e}")

    return {"task_id": tid}
PY
fi

# 4) Point Uvicorn (in compose) to app.asgi:app instead of app.main:app
#    This replaces any 'app.main:app' occurrences.
if [ -f docker-compose.yml ]; then
  sed -i -E 's/app\.main:app/app.asgi:app/g' docker-compose.yml
fi

echo "Patched. Showing first lines of app/asgi.py:"
nl -ba app/asgi.py | sed -n '1,20p'
