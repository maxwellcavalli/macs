import os, asyncpg, typing as t

class TaskRepo:
    def __init__(self, dsn: str|None=None, **kw):
        self.dsn = dsn
        self.kw = kw

    @classmethod
    def from_env(cls):
        dsn = os.getenv("DB_DSN") or os.getenv("DATABASE_URL")
        if dsn:
            if dsn.startswith("postgresql+asyncpg://"):
                dsn = "postgresql://" + dsn.split("://", 1)[1]
            elif dsn.startswith("postgresql+psycopg://"):
                dsn = "postgresql://" + dsn.split("://", 1)[1]
            return cls(dsn=dsn)
        host = (
            os.getenv("PGHOST")
            or os.getenv("POSTGRES_HOST")
            or "postgres"
        )
        port = int(os.getenv("PGPORT", "5432"))
        user = (
            os.getenv("PGUSER")
            or os.getenv("POSTGRES_USER")
            or "postgres"
        )
        password = (
            os.getenv("PGPASSWORD")
            or os.getenv("POSTGRES_PASSWORD")
            or "postgres"
        )
        database = (
            os.getenv("PGDATABASE")
            or os.getenv("POSTGRES_DB")
            or os.getenv("DB_NAME", "macs")
        )
        return cls(host=host, port=port, user=user, password=password, database=database)

    async def _connect(self):
        if self.dsn:
            return await asyncpg.connect(self.dsn)
        return await asyncpg.connect(**self.kw)

    async def get_by_id(self, task_id: str) -> t.Optional[dict]:
        conn = await self._connect()
        try:
            row = await conn.fetchrow("SELECT to_jsonb(t) AS j FROM public.tasks t WHERE id=$1", task_id)
            if not row:
                return None
            return dict(row["j"])
        finally:
            await conn.close()
