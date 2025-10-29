# Persistent Workspace Memory — Development Plan

## Goals
- Capture and persist task context (prompt, repo paths, selected model, outputs) so future jobs can reuse local knowledge.
- Provide lightweight search APIs to retrieve prior work scoped to the same repository or language.
- Keep the solution offline-first and compatible with the existing Postgres footprint.

## Current System Summary
- `app/queue.JobQueue` orchestrates executions and already writes artifacts/zips for SSE completion.
- Task metadata and status live in Postgres tables (`tasks`, `rewards`, `bandit_stats`).
- No durable store exists for previous completions beyond artifacts on disk and the JSONL bandit log.

## Proposed Architecture
### Storage Model
- Extend Postgres with a new table `workspace_memories`:
  - `id UUID PK`, `task_id UUID`, `repo_path TEXT`, `language TEXT`, `goal TEXT`, `model TEXT`.
  - `mode TEXT`, `status TEXT`, `created_at TIMESTAMPTZ`.
  - `artifact_rel TEXT`, `zip_rel TEXT`, `files JSONB` (per-file content or hashes).
  - `summary TEXT`, `embedding VECTOR` (optional, null until pgvector enabled).
- Add GIN index on `language`, `repo_path`, and `status`, plus full-text index on `summary` when available.
- Keep embeddings optional: feature-gate behind `WORKSPACE_MEMORY_EMBEDDINGS=1` and stub out generation for v1.

### Ingestion Flow (Execution Control Touchpoints)
- Hook `JobQueue._runner` success paths (single + duel winner) to call `memory.record_completion(...)`.
- `memory.record_completion` should:
  1. Build a normalized payload (task id, input goal, repo include globs, selected model, compile/test results).
  2. Load or summarize generated files (limit size, store hashes/first N chars).
  3. Optionally compute an embedding (later iteration).
  4. Insert into `workspace_memories`.
- Ensure cancellations/errors skip ingestion. Record failures via structured logs for observability.

### Retrieval Flow
- Add `app/memory.py` with:
  - `record_completion()`, `search_memories(repo_path, language, query, limit=5)`.
  - Fallback to simple `ILIKE` search across `goal`/`summary` when embeddings disabled.
- Expose FastAPI routes:
  - `GET /v1/memory/search?repo=...&language=...&q=...` (requires API key).
  - `GET /v1/memory/{memory_id}` to return detailed payload including artifact paths.
- Reuse existing `require_api_key` guard; respect rate-limiter for new endpoints.

### Configuration & Settings
- Extend `app/settings.Settings` with `workspace_memory_enabled: bool` and `workspace_memory_embeddings: bool`.
- Guard ingestion and API routes behind the feature flag for staged rollout.
- Add env defaults to `.env.example` (or README) once available.

## Data & Migration Plan
1. Add a Flyway migration under `flyway/sql/` to create `workspace_memories` (table + indexes).
2. Follow-on migration `V1003__workspace_memory_nullable_task.sql` relaxes `task_id` so bootstrap records can omit a task reference.
3. Backfill initial data by scanning existing artifacts (optional stretch).
4. For local dev, include seed script for sample records to exercise search UI.

## Testing Strategy
- Unit tests for `memory.record_completion` (handles truncation, disabled flag).
- Integration tests hitting `/v1/memory/search` with in-memory SQLite (or Postgres test container) to assert filters and permissions.
- Regression tests in `tests/integration_smoke.sh` to ensure feature flag OFF has no side-effects.

## Documentation & UX
- Update `README.md` with feature overview and enabling instructions.
- Add section to `docs/roadmap.md` linking to this plan and tracking status.
- Consider minimal UI surfacing (e.g., `/lab` panel) in a follow-up milestone.

## Open Questions
- Do we require embeddings in v1, or is text search sufficient?
- How aggressively should we store file contents (full text vs. hashed plus path)?
- Should duel losers also populate memory for “bad” examples?

## Risks
- Potential database growth if large artifacts are stored unabated; mitigate via size caps and pruning policy.
- Additional load on `JobQueue` thread; ensure ingestion is async and non-blocking.
- Security: ensure stored artifacts respect workspace governance (no secret leakage).

## Implementation Checklist
1. Add settings/env toggles and feature flag plumbing.
2. Write Alembic migration for `workspace_memories`.
3. Implement `app/memory.py` module with record/search logic.
4. Integrate ingestion calls inside `JobQueue` success paths.
5. Add FastAPI routes and schemas for search/detail.
6. Backfill logging/metrics (counter for memory writes, search hits).
7. Add bootstrap CLI (`tools/memory_ingest_repo.py`) to ingest existing repo files and expose Makefile shortcut.
8. Cover with unit/integration tests; update smoke script.
9. Document feature and rollout steps.
