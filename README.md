# MACS — Local Dev Stack (API + Postgres + Ollama + Prometheus + Grafana)

This repo ships a single `docker-compose.yml` that brings up everything you need:
- **API** (host `8080`, overridable)
- **Postgres** (host `55432`, overridable)
- **Ollama** (GPU; internal-only by default)
- **Prometheus** (host `39090`)
- **Grafana** (host `33000`)

> **Requirements**: Docker + Docker Compose v2. For GPU, enable NVIDIA GPU support (Docker Desktop → Settings → Resources → GPU) or install NVIDIA Container Toolkit on Linux.

---

## 1) Quickstart

```bash
# (one time) Create an API key so the API can boot
printf "API_KEY=dev-%s
" "$(openssl rand -hex 16)" > .env

# Build and start everything
docker compose up -d --build

# See status
docker compose ps

### Tunable runtime settings

The API and runner expose a few environment variables that influence how quickly results surface and whether a request is evaluated by one or multiple models. Defaults are set in `docker-compose.yml`, and you can override them per deployment:

| Variable | Purpose | Default |
|----------|---------|---------|
| `SSE_DB_POLL_INTERVAL` | How often (seconds) the SSE stream polls the database once an artifact isn’t found immediately. Lower values surface results faster but incur more DB queries. | `1.0` |
| `FINAL_WAIT_SECONDS` | Upper bound (seconds) that `/v1/tasks/{id}/final` will wait before returning `404`. Helps avoid the initial 404 seen during cold starts. | `60.0` |
| `FINAL_WAIT_INTERVAL` | How frequently the `/final` endpoint re-checks for artifacts during that wait window. | `0.2` |
| `SSE_FINAL_WAIT_SECONDS` | How long SSE waits for the persisted final payload before emitting a `done` event. | `120.0` |
| `FORCE_DUEL` | When set to `1`, every task runs in duel mode (two models compete, best result returned). Leave at `0` to let the router decide per request. | `1` |
| `DUEL_TIMEOUT_SEC` | Maximum seconds to wait for both duel candidates before picking a winner. | `240` |
| `CANDIDATE_TIMEOUT_SEC` | Per-model generation timeout used by the queue. | `240` |

You can also flip duel mode per request by adding `metadata.force_duel = true` to the task payload.
```

### Health checks

```bash
# API health (no auth)
curl -fsS "http://127.0.0.1:${API_HOST_PORT:-8080}/health"

# Read your API key (for protected endpoints)
API_KEY=$(grep -E '^API_KEY=' .env | cut -d= -f2)

# Ollama health proxied via API (requires x-api-key)
curl -fsS -H "x-api-key: $API_KEY" "http://127.0.0.1:${API_HOST_PORT:-8080}/v1/ollama/health"

# Prometheus readiness
curl -fsS "http://127.0.0.1:${PROM_HOST_PORT:-39090}/-/ready" || true
```

---

## 2) Default URLs

- **API**
  - Health: `http://127.0.0.1:${API_HOST_PORT:-8080}/health`
  - Example (proxied): `http://127.0.0.1:${API_HOST_PORT:-8080}/v1/ollama/health`  
    _Header_: `x-api-key: <API_KEY from .env>`

- **Grafana**: `http://127.0.0.1:${GRAFANA_HOST_PORT:-33000}`  
  _Login_: `admin / admin` (change with `GF_ADMIN_USER` / `GF_ADMIN_PASSWORD`)

- **Prometheus**: `http://127.0.0.1:${PROM_HOST_PORT:-39090}`

- **Postgres (host DSN)**:  
  `postgres://macs:macs@127.0.0.1:${PG_HOST_PORT:-55432}/macs`

- **Ollama**: internal-only (`http://ollama:11434` inside Docker network).  
  If you need host access, add to compose: `ports: ["127.0.0.1:21434:11434"]` and use `http://127.0.0.1:21434/`.

---

## 3) Common tasks

```bash
# Rebuild API only (after code changes)
docker compose build api && docker compose up -d api

# Tail logs
docker compose logs -f api
docker compose logs -f postgres
docker compose logs -f ollama
docker compose logs -f prometheus
docker compose logs -f grafana

# Stop (keep data volumes)
docker compose down

# Full reset (⚠ removes DB, models, artifacts)
docker compose down -v
```

---

## 4) Port overrides (when something else is using the default)

All host ports can be changed on the fly:

```bash
API_HOST_PORT=18080 PG_HOST_PORT=56432 PROM_HOST_PORT=49090 GRAFANA_HOST_PORT=43000 docker compose up -d
```

---

## 5) GPU notes

- Compose uses `gpus: all` for **Ollama**.  
- If you don’t have GPU support, either enable it or remove the `gpus:` and `deploy.resources.reservations.devices` lines in `docker-compose.yml`.

---

## 6) Troubleshooting

- **“API_KEY missing”** — ensure `.env` exists with `API_KEY=...` (Compose auto-loads `.env`).  
- **Port conflicts** — bump the host port envs above (e.g., `API_HOST_PORT=18080`).  
- **Postgres doesn’t start** — try another host port (`PG_HOST_PORT=56432`) or stop a local Postgres.  
- **Grafana login** — defaults to `admin / admin` unless changed via env.

---

## 7) Service summary

| Service    | Host Port (default) | Internal | Notes                                        |
|------------|----------------------|----------|----------------------------------------------|
| API        | 8080                 | 8080     | Protected routes require `x-api-key`         |
| Postgres   | 55432                | 5432     | `postgres://macs:macs@127.0.0.1:55432/macs`  |
| Prometheus | 39090                | 9090     | Scrapes API `/metrics`                       |
| Grafana    | 33000                | 3000     | Pre-provisioned Prometheus datasource        |
| Ollama     | _none_               | 11434    | Internal-only by default (GPU)               |

---

## 8) Workspace memory (opt-in)

- Enable persistence with `WORKSPACE_MEMORY_ENABLED=1` (optional embeddings flag: `WORKSPACE_MEMORY_EMBEDDINGS=0/1`).
- Completed tasks are stored in `workspace_memories` via the queue; data remains in Postgres.
- Query recent results with `GET /v1/memory/search?repo=...&language=...&query=...` (requires API key).
- Fetch a specific record with `GET /v1/memory/{memory_id}`.
- Disable the feature by omitting the env var or setting it to `0`.
- Bootstrap existing files: `make memory-ingest` (or run `tools/memory_ingest_repo.py --root ./workspace`), then restart the API so new context is available to chat prompts.

---

## 9) Agent CLI

Install the package locally (`pip install -e .`) to expose the `agentctl` command.

- Chat once: `agentctl chat "hello" --language python --download`  
  This streams the task, prints the answer, and saves the zip to `workspace/zips/`.
- Attach context: `agentctl chat "review the repo" --attach uploads.zip` uploads the archive via `/v1/memory/upload` before creating the task.
- Generate code: `agentctl code "Create HelloController" --language java --expected-file src/main/java/...` waits for completion and prints follow-up steps.
- Stay in a session: `agentctl chat-session --attach repo.zip` opens an interactive REPL (prompts list commands like `/attach`, `/download`, `/exit`).
- Inspect tasks: `agentctl status <task-id>` and `agentctl download --id <task-id>` retrieve status and artifacts.
- Raw payloads still work: `agentctl submit task.json` and `agentctl feedback feedback.json`.

Set `API_URL` / `API_KEY` env vars (or pass `--api-url`, `--api-key`) so the CLI can authenticate against your running API.

---

Happy shipping! 🚀
