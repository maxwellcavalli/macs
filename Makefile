# --- config ---------------------------------------------------
SHELL := /bin/bash
.RECIPEPREFIX := >
COMPOSE ?= docker compose
API_SVC ?= macs-api
DB_SVC  ?= macs-db
OLLAMA_SVC ?= ollama
API_URL ?= http://localhost:8080
API_KEY ?= dev-local

# jq filter: pass only JSON lines (drop uvicorn text)
JSONLINES = sed -n 's/^\({.*}\)$/\1/p'

# --- lifecycle ------------------------------------------------
.PHONY: up down restart build ps logs logs-json
up:            ## Start stack in background
> $(COMPOSE) up -d

down:          ## Stop stack
> $(COMPOSE) down

build:         ## Rebuild API image
> $(COMPOSE) build api

restart:       ## Restart API service
> $(COMPOSE) restart api

ps:            ## Show compose services
> $(COMPOSE) ps

# --- logs -----------------------------------------------------
logs:          ## Follow raw API logs
> docker logs -f $(API_SVC)

logs-json:     ## Follow JSON-only app logs (jq pretty)
> docker logs -f $(API_SVC) | $(JSONLINES) | jq .

# --- health ---------------------------------------------------
.PHONY: health ohealth metrics
health:        ## API health
> curl -s $(API_URL)/health | jq .

ohealth:       ## Ollama health via API
> curl -s $(API_URL)/v1/ollama/health | jq .

metrics:       ## Prometheus scrape (grep duel counters)
> curl -s $(API_URL)/metrics | grep -E 'duel_(rule|selection)_decisions_total|router_route_count' || true

# --- DB -------------------------------------------------------
.PHONY: psql alembic-current alembic-upgrade
psql:          ## Open psql into DB container
> docker exec -it $(DB_SVC) psql -U agent -d agent

alembic-current: ## Show current alembic head
> docker exec -it $(API_SVC) alembic current

alembic-upgrade: ## Upgrade to head
> docker exec -it $(API_SVC) alembic upgrade head

# --- quick tasks ---------------------------------------------
.PHONY: models duel cancel stream ping
models:        ## List discovered models (debug=1)
> curl -s "$(API_URL)/v1/models?debug=1" | jq .

duel:          ## Submit a Java duel (scaffolded Maven if needed)
> printf '%s\n' '{' \
> '  "type": "CODE",' \
> '  "input": {' \
> '    "language": "java",' \
> '    "frameworks": [],' \
> '    "repo": { "path": "./workspace", "include": [], "exclude": [] },' \
> '    "constraints": { "max_tokens": 2048, "latency_ms": 120000 },' \
> '    "goal": "Create a single-file Java class that compiles using only the JDK."' \
> '  },' \
> '  "routing_hints": { "duel": true },' \
> '  "output_contract": { "expected_files": ["src/main/java/com/acme/DuelDemo.java"] }' \
> '}' > /tmp/duel.quick.json
> curl -s -X POST "$(API_URL)/v1/tasks" \
>   -H "X-API-Key: $(API_KEY)" -H "Content-Type: application/json" \
>   -d @/tmp/duel.quick.json | tee /tmp/duel.quick.out | jq .
> echo "Task id saved to /tmp/duel.quick.out"

ping:          ## Submit a single-candidate Java task
> printf '%s\n' '{' \
> '  "type": "CODE",' \
> '  "input": {' \
> '    "language": "java",' \
> '    "frameworks": [],' \
> '    "repo": {"path":"./workspace","include":[],"exclude":[]},' \
> '    "constraints": { "max_tokens": 256, "latency_ms": 30000 },' \
> '    "goal": "Emit a compilable single-file Java class using only JDK."' \
> '  },' \
> '  "routing_hints": { "duel": false },' \
> '  "output_contract": { "expected_files": ["src/main/java/com/acme/Ping.java"] }' \
> '}' > /tmp/ping.task.json
> curl -s -X POST "$(API_URL)/v1/tasks" \
>   -H "X-API-Key: $(API_KEY)" -H "Content-Type: application/json" \
>   -d @/tmp/ping.task.json | tee /tmp/ping.task.out | jq .
> echo "Task id saved to /tmp/ping.task.out"

# --- stream & cancel -----------------------------------------
stream:        ## Stream SSE for last task (uses /tmp/*.out)
> test -f /tmp/duel.quick.out -o -f /tmp/ping.task.out || (echo "no task id found; run 'make duel' or 'make ping' first" && exit 1)
> TASK_ID=$$(jq -r '.task_id' /tmp/duel.quick.out 2>/dev/null || jq -r '.task_id' /tmp/ping.task.out); \
>   echo "Streaming $$TASK_ID..."; \
>   curl -N "$(API_URL)/v1/stream/$$TASK_ID"

cancel:        ## Cancel last task
> test -f /tmp/duel.quick.out -o -f /tmp/ping.task.out || (echo "no task id found; run 'make duel' or 'make ping' first" && exit 1)
> TASK_ID=$$(jq -r '.task_id' /tmp/duel.quick.out 2>/dev/null || jq -r '.task_id' /tmp/ping.task.out); \
>   curl -s -X POST "$(API_URL)/v1/tasks/$$TASK_ID/cancel" \
>     -H "X-API-Key: $(API_KEY)" | jq .

# --- shell ----------------------------------------------------
.PHONY: sh-api sh-db
sh-api:        ## Shell into API container
> docker exec -it $(API_SVC) bash

sh-db:         ## Shell into DB container
> docker exec -it $(DB_SVC) bash

# --- lint/format ---------------------------------------------
.PHONY: fmt lint
fmt:           ## Run black/ruff (if present)
> -docker exec -it $(API_SVC) bash -lc 'black app || true'

lint:
> -docker exec -it $(API_SVC) bash -lc 'ruff check app || true'

# --- help -----------------------------------------------------
.PHONY: help
help:          ## Show this help
> @grep -E '^[a-zA-Z0-9_-]+:.*?## ' Makefile | sed 's/:.*## /:\t/g' | sort

.PHONY: ci-local
ci-local:      ## Run integration smoke test locally
> API_URL="$(API_URL)" API_KEY="$(API_KEY)" bash tests/integration_smoke.sh
.PHONY: ci-local
# DUPLICATE ci-local (commented out below)
# ci-local:      ## Run integration smoke test locally
# > API=$(API_URL) API_KEY=$(API_KEY) bash tests/integration_smoke.sh


# ---- Database (Flyway) ----
db-info:
> ./scripts/flyway.sh info

db-migrate:
> ./scripts/flyway.sh migrate

db-baseline-0:
> ./scripts/flyway.sh baseline -baselineVersion=0

db-validate:
> ./scripts/flyway.sh validate

db-repair:
> ./scripts/flyway.sh repair

db-clean:
> ./scripts/flyway.sh clean

bandit-seed: ## Replay earlier bandit totals into the DB
> ./scripts/bandit_seed.sh
.PHONY: rag-eval rag-gold-init
# RAG eval config (override as needed)
RAG_GOLD ?= data/golden_set.jsonl
RAG_K ?= 5
RAG_REPORT ?= artifacts/rag_eval/report.json

rag-gold-init:
> @mkdir -p data
> @test -s $(RAG_GOLD) || { \
> echo '{"query":"hello","answer_doc":"docA"}' > $(RAG_GOLD); \
> echo '{"query":"world","answer_doc":"docB"}' >> $(RAG_GOLD); \
> echo "Seeded $(RAG_GOLD)"; \
> }

rag-eval: ## Run retrieval eval and write a JSON report
	@mkdir -p $(dir $(RAG_REPORT))
	@python -m app.rag_eval --gold $(RAG_GOLD) --k $(RAG_K) --report $(RAG_REPORT)
	@echo "Wrote $(RAG_REPORT)"
