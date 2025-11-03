# Workspace Memory Code Upload — Design

## Goals
- Allow users to upload a lightweight snapshot of code or documentation directly via the chat UI.
- Ingest uploaded files into `workspace_memories` scoped to the active session so the assistant can immediately reference them.
- Keep uploads isolated, secure, and bounded in size to avoid polluting global history.

## UX Summary
1. User clicks “Attach code” in the chat sidebar and selects a ZIP archive or drops files.
2. Frontend sends the archive to the authenticated endpoint (`POST /v1/memory/upload`) along with an optional session identifier.
3. API unpacks the archive into a temp directory, normalises file paths, truncates content, and writes a single aggregate `workspace_memories` row (mode `upload`) scoped to the session, containing a manifest plus snippets.
4. API responds with the generated memory ID + summary.
5. Chat UI refreshes the memory panel and auto selects the uploaded bundle for the next prompt.
6. When the chat ends (or after a TTL), uploaded entries can be cleaned up via an async job to keep the table lean.

## API Requirements
- Endpoint: `POST /v1/memory/upload`
  - Auth: reuse `require_api_key`.
  - Request: multipart form with fields:
    - `file`: required ZIP/TAR archive (limit ~10 MB).
    - `repo_path`: optional label (default `session-{uuid}`).
    - `session_id`: client-provided UUID to group uploads per chat session.
  - Response: `{ "memories": [ { "id": ..., "goal": ..., "summary": ... }, ... ] }`
- Validation:
  - Reject archives exceeding size limit or containing more than N files (e.g., 200).
  - Skip binary files; only ingest text up to `MAX_FILE_BYTES`.
  - Enforce safe extraction to a temp dir (guard against path traversal).
- Ingestion:
  - Aggregate file summaries/snippets and insert a single row via `record_upload_bundle` with `mode="upload"`, `task_id=NULL`, and session scoping.
- Indexing:
  - Consider adding an index on `mode` and `session_id` to make cleanup/filtering efficient.

## UI Changes
- Add an “Attach code” button next to “Find related work”.
- Implement a modal or drop zone that accepts a single ZIP.
- After upload succeeds, call `fetchMemories` with `session_id` to refresh the panel.
- Persist `session_id` in localStorage per chat; include it in downstream requests (tasks and uploads).
- Display upload progress + validation errors in the sidebar.

## Cleanup Strategy
- Add optional `session_id` and `expires_at` columns to `workspace_memories` (future migration).
- Introduce a background job/command (`tools/memory_gc.py`) that deletes `mode='upload'` rows older than N hours.
- Alternatively, delete session-specific rows when the UI calls a `/v1/memory/session/{id}/clear` endpoint.

## Security Considerations
- Require API key for uploads.
- Limit archive size and number of files; reject if compressed or uncompressed size exceeds thresholds.
- Use `zipfile` with strict path normalisation to avoid writing outside temp dir.
- Sanitize stored content (truncate, drop null bytes).
- Log upload metadata (number of files, size) for audit.

## Open Questions
- Do uploads need to respect repo inclusion filters (e.g., only under `workspace/`)? For now, rely on session scoping.
- Should we allow plain text drag-and-drop (paste code) in addition to ZIP? Future enhancement.
- How long should uploaded memories persist? Default proposal: 24 h unless explicitly cleared.

## Next Steps
1. Implement backend endpoint + ingestion helpers.
2. Extend DB schema with `session_id`/`mode` indexes if needed.
3. Build UI uploader and session management in chat panel.
