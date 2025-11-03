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

class TaskInput(BaseModel):
    goal: str = Field(..., min_length=1)
    language: str = "python"
    repo: Dict[str, Any] = Field(default_factory=dict)
    constraints: Dict[str, Any] = Field(default_factory=dict)
    model: str = "qwen2.5:7b"
    options: Dict[str, Any] = Field(default_factory=dict)

class TaskCreate(BaseModel):
    type: Literal["CODE","PLAN","REFACTOR","TEST","DOC"]
    input: TaskInput
    metadata: Dict[str, Any] = Field(default_factory=dict)
    template_ver: Optional[int] = None

router = APIRouter()

@router.post("/v1/tasks")
async def create_task(body: TaskCreate):
    # visible log so we know THIS handler ran
    from datetime import datetime as _dt
    print({"ts": _dt.utcnow().isoformat()+"Z", "msg": "create_task_fix invoked", "goal": body.input.goal[:80]}, flush=True)

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
