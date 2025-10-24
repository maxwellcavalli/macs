from __future__ import annotations
from typing import Optional
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine, AsyncConnection
from sqlalchemy import text
from .settings import settings

_engine: Optional[AsyncEngine] = None

STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS tasks (
      id UUID PRIMARY KEY,
      type TEXT NOT NULL,
      language TEXT,
      created_at TIMESTAMPTZ DEFAULT now(),
      status TEXT NOT NULL,
      latency_ms INT,
      model_used TEXT,
      template_ver TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS rewards (
      id UUID PRIMARY KEY,
      task_id UUID REFERENCES tasks(id) ON DELETE CASCADE,
      model TEXT NOT NULL,
      success BOOLEAN NOT NULL,
      latency_ms INT,
      human_score INT,
      created_at TIMESTAMPTZ DEFAULT now()
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS bandit_stats (
      model TEXT NOT NULL,
      feature_hash TEXT NOT NULL,
      runs INT DEFAULT 0,
      reward_sum DOUBLE PRECISION DEFAULT 0,
      reward_sq_sum DOUBLE PRECISION DEFAULT 0,
      last_updated TIMESTAMPTZ DEFAULT now(),
      PRIMARY KEY (model, feature_hash)
    );
    """
]

async def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    return _engine

async def init_db():
    eng = await get_engine()
    async with eng.begin() as conn:
        for stmt in STATEMENTS:
            await conn.execute(text(stmt))

async def insert_task(conn: AsyncConnection, id, type_, language, status, template_ver=None):
    await conn.execute(text("""
        INSERT INTO tasks(id, type, language, status, template_ver)
        VALUES (:id, :type, :language, :status, :template_ver)
    """), dict(id=str(id), type=type_, language=language, status=status, template_ver=template_ver))

async def update_task_status(conn: AsyncConnection, id, status, model_used=None, latency_ms=None):
    await conn.execute(text("""
        UPDATE tasks SET status=:status, model_used=COALESCE(:model_used, model_used),
                         latency_ms=COALESCE(:latency_ms, latency_ms)
        WHERE id=:id
    """), dict(id=str(id), status=status, model_used=model_used, latency_ms=latency_ms))

async def get_task(conn: AsyncConnection, id):
    res = await conn.execute(text("""
        SELECT id, status, model_used, latency_ms, template_ver FROM tasks WHERE id=:id
    """), dict(id=str(id)))
    return res.first()
