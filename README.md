# Multi‑Agent Code System — Phase 1 MVP (v24.0)

Local, offline‑first skeleton implementing the Phase‑1 plan: API, queue, SSE heartbeats, cancel/resume, filesystem/exec sandbox scaffolding, Postgres baseline, model registry with VRAM probe, metrics & tracing, and CLI.

## Run (no Docker)

1. Create and activate a virtualenv (or use `uv`).
2. Install deps:

```bash
pip install -r requirements.txt
# or
pip install .
```

3. Ensure Postgres is running locally and the URL in `.env` is correct (defaults to `postgresql+asyncpg://agent:agent@localhost:5432/agent`).
4. Initialize schema (automatically on first start). Optionally run Alembic:

```bash
alembic upgrade head
```

5. Start the API:

```bash
uvicorn app.main:app --reload --port 8080
```

## Run (Docker Compose)

```bash
docker compose up --build
```

The API will be at http://localhost:8080 . Health at `/health`, Prometheus at `/metrics`.

## API (MVP)

- `POST /v1/tasks` (API key required) → `{task_id}`
- `GET  /v1/tasks/{id}` → task status
- `POST /v1/tasks/{id}/cancel` (API key) → cancel
- `GET  /v1/stream/{id}` → Server‑Sent Events (includes heartbeats)
- `POST /v1/feedback` (API key) → store feedback
- `GET  /v1/models` → available models filtered by VRAM and language

Auth: set header `X-API-Key: <API_KEY>` (defaults to `dev-local` from `.env`).

## CLI

```bash
export API_KEY=dev-local
agentctl submit task.json
agentctl status <uuid>
agentctl cancel <uuid>
agentctl feedback feedback.json
```

## Example task payload (v1.1)

```json
{
  "type": "CODE",
  "input": {
    "language": "java",
    "frameworks": ["spring-boot", "r2dbc", "graphql"],
    "repo": {"path": "./workspace", "include": ["src/**"], "exclude": ["**/target/**"]},
    "constraints": {"max_tokens": 2048, "latency_ms": 60000, "style": "clean-arch"},
    "goal": "Generate Product resolver and tests"
  },
  "output_contract": {
    "expected_files": ["src/main/java/com/acme/product/ProductResolver.java"]
  },
  "non_negotiables": {"build_tool": "gradle", "jdk": 21},
  "oracle": {"smoke": true, "full": false}
}
```

## Notes

- Filesystem writes are restricted to `WORKSPACE_ROOT` (`./workspace` by default). An attempted write outside is denied and audited.
- Exec sandbox only allows a small tool allowlist (javac/mvn/gradlew/pytest/etc.) with timeouts; network egress is not allowed by design.
- VRAM probe uses `nvidia-smi` when present to filter models by `min_vram_gb`.
- Metrics include `router_route_count`, `compile_pass_total`, `test_smoke_pass_total`.
- Tracing is configured to console exporter by default; wire OTLP to the collector via env if desired.

## What’s next (Phase‑2/3 hooks are stubbed)

- Feedback reward computation & contextual bandit.
- BM25+symbol retrieval & exemplar injection.
- Planner → Coder → Tester → Reviewer loop and Duel mode.

This repo intentionally favors clarity and bootstrap-ability on WSL2.
