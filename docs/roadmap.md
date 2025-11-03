# MACS Feature Roadmap

## 1. Persistent Workspace Memory
- **Goal:** Allow agents to reuse prior task output, repo diffs, and execution context.
- **Approach:** Index generated artifacts, chosen code edits, and task metadata into a lightweight vector or kv store keyed by repo/task.
- **Benefits:** Improves follow-up fix quality and reduces repeated clarifying prompts.
- **Dependencies:** Decide on storage (SQLite, DuckDB, or local vector store), extend queue to emit embeddings, add retrieval utilities.

## 2. Historical Chat Threads
- **Goal:** Store `/chat` interactions (messages, artifacts, metadata) so users can resume conversations.
- **Approach:** Persist chat transcripts in Postgres with task references; expose `/v1/chat/{thread_id}`; enhance chat UI with history picker.
- **Benefits:** Enables context continuity and audit of assistant guidance.
- **Dependencies:** DB migrations, new ORM helpers, UI changes for session management.

## 3. Model Learning Loop
- **Goal:** Continuously refine model selection using completed tasks and human feedback.
- **Approach:** Batch ingest historical rewards into `bandit_stats`, compute confidence metrics, surface Grafana dashboards, optionally retrain offline models.
- **Benefits:** Drives objective improvements in routing accuracy and task success.
- **Dependencies:** Scheduled job (cron or async worker), dashboard updates, storage for aggregated metrics.

## 4. Artifact Browser
- **Goal:** Inspect generated files directly through the API/UI without manual downloads.
- **Approach:** Add `/v1/artifacts/{task_id}` for structured listings and file fetch; extend `/chat` or `/lab` UIs with artifact viewers.
- **Benefits:** Faster validation of agent output; simpler QA flows.
- **Dependencies:** Auth checks, streaming endpoints for large files, front-end components.

## 5. Policy & Audit Enhancements
- **Goal:** Tighten governance around model usage and filesystem access.
- **Approach:** Expand `governance.py` rules to support per-model policies, integrate Prometheus counters for denies, and surface alerts.
- **Benefits:** Improves compliance posture and observability for security-sensitive deployments.
- **Dependencies:** Policy schema updates, metrics wiring, alert rules.

## 6. Benchmark & Regression Harness
- **Goal:** Detect performance regressions via staged, repeatable task suites.
- **Approach:** Build scripted scenarios invoking `tools/runner.py`, record compile/test pass rates, and compare against baselines.
- **Benefits:** Ensures feature work does not degrade core success metrics.
- **Dependencies:** Task fixture library, report generator, CI integration.
