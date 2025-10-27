# Project Overview

This repository powers the **MACS** (Multi-Agent Code System) developer stack. It bundles a FastAPI backend, long-running runner process, Ollama inference, PostgreSQL storage, and a Tailwind-based chat UI. The goal is to accept code-generation requests, orchestrate model calls, stream back progress, and materialise artefacts (code files, zips, metrics) locally.

---

## Core Services

| Service  | Role | Key Files |
|----------|------|-----------|
| `api`    | FastAPI application that exposes REST + SSE endpoints, serves the UI, tracks tasks, and proxies artefacts. | `app/main.py`, `app/api.py`, `app/final_api.py`, `app/static/*` |
| `runner` | Async worker that dequeues tasks from Postgres and issues streaming calls to Ollama. | `tools/runner.py` |
| `postgres` | Primary datastore for tasks, task events, artefacts metadata, and bandit statistics. | `flyway/sql/*.sql` |
| `ollama` | Local model runtime. Models are pulled at bootstrap and served at `http://ollama:11434`. | `docker-compose.yml`, `app/llm/ollama_client.py` |

`docker-compose.yml` wires the services together (API, runner, Postgres, Ollama, Grafana/Prometheus optional), mounting local directories for artefacts (`./artifacts`) and generated zips (`./workspace/zips`).

---

## Task Lifecycle (API + Runner)

1. **Submit** – Clients call `POST /v1/tasks` with a `TaskV11` payload. Validation lives in `app/schemas.py`; compatibility routes are in `app/routers/tasks_create_fix.py`.
2. **Persist** – The API inserts a `tasks` row (status `queued`) via `app/db.py::insert_task`. Runner also logs `task_events` as deltas arrive.
3. **Execute** – `tools/runner.py` locks and updates the task to `running`, streams tokens from Ollama (`/api/generate`), and records deltas (`delta` events). Failures bubble into the `error` column.
4. **Finalise** – The queue (`app/queue.py`) or runner writes the final response, updates `tasks.status`, and produces structured artefacts:
   * `artifacts/<task_id>/result.json` with the streaming payload.
   * Optional `result.md`/`response.md`.
   * Generated ZIP under `/data/zips/<task_id>.zip`.
5. **Consume** – Clients stream updates via `GET /v1/stream/{task_id}` (SSE), poll `/v1/tasks/{task_id}`, or fetch the final payload at `/v1/tasks/{task_id}/final` / `/v1/tasks/{task_id}/zip`.

---

## Chat UI (`/chat`)

* Static assets live in `app/static/chat/index.html`. The UI uses CDN Tailwind, Marked, and Highlight.js.
* Messages are posted to `POST /v1/tasks` with `metadata.mode_hint="chat"` so the router routes conversationally.
* SSE is consumed at `/v1/stream/{task_id}`; the UI listens to both default `message` and custom `event: done`.
* A “Download ZIP” button appears automatically when payloads include `zip_url`.

Prompt guidance ensures the model emits real files:

```
File: src/Main.java
```java
// …
```
```

The queue parses fenced blocks and re-creates the filesystem inside the sandbox before packaging.

---

## Key Modules & Helpers

| Module | Responsibility |
|--------|----------------|
| `app/queue.py` | In-process work queue for API-streamed tasks. Detects prompt mode, sanitises code, packages artefacts, emits SSE updates. |
| `app/zips.py` | Utility to write per-task zip archives under `/data/zips`. |
| `app/sse.py` | Lightweight pub/sub hub for SSE streams. |
| `app/final_api.py` | Final payload endpoint with DB-first lookup and fallback to `artifacts/`. |
| `app/bandit*.py` | Multi-armed bandit logic for model ranking. |
| `scripts/*.sh` | Diagnostics, validation, and CLI helpers (submit tasks, seed bandit stats, etc.). |

---

## Storage Layout

* `artifacts/<task_id>/` – Raw JSON + markdown, produced by queue or runner.
* `workspace/zips/<task_id>.zip` – Generated archives (bind-mounted as `/data/zips` in containers).
* `workspace/` – General sandbox where generated code and temporary files are placed.

Make sure these directories exist locally before running (`mkdir -p artifacts workspace/zips`).

---

## Useful Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /v1/tasks` | Submit a task (requires `x-api-key`). |
| `GET /v1/stream/{task_id}` | Server-Sent Events stream for task updates. |
| `GET /v1/tasks/{task_id}` | Fetch DB snapshot (status, timings). |
| `GET /v1/tasks/{task_id}/final` | JSON payload with result, metadata, `zip_url`. |
| `GET /v1/tasks/{task_id}/zip` | Download the task archive. |
| `GET /zips/{filename}` | Direct zip download by filename. |
| `GET /chat` | Rich chat UI for interactive requests. |

---

## Local Development Tips

1. Install prerequisites (`docker`, `docker compose`, optional GPU drivers for Ollama).
2. Create the bind-mounted directories:
   ```bash
   mkdir -p artifacts workspace/zips
   ```
3. Launch the stack:
   ```bash
   docker compose up -d --build
   ```
4. Seed models (example):
   ```bash
   docker compose exec ollama ollama pull qwen2.5-coder:7b-instruct-q4_K_M
   ```
5. Try the chat UI at `http://localhost:8080/chat` or use CLI scripts (`scripts/submit_task.sh`).

Resetting artefacts or zips is as simple as deleting the host directories; they are regenerated per task.

---

## Next Steps / Extensibility

* **Binary assets** – The zip utility supports arbitrary content; emit base64 in fenced blocks and decode in `_extract_files_from_content`.
* **Model catalog** – `config/models.yaml` merges statically-defined models with Ollama discovery. Update tags there to control available options.
* **Prometheus/Grafana** – Optional compose services for observability (`docker compose up grafana prometheus`).
* **Worker deprecation** – The legacy `worker` service is unneeded; use `runner` for the modern pipeline.

Keep this document around to quickly recall how tasks flow, where artefacts land, and which components to tweak when adding new capabilities (e.g., scaffolding templates, linting, additional download formats).

