.RECIPEPREFIX := >
SHELL := /bin/bash
.SHELLFLAGS := -euo pipefail -c
PY ?= python3

.DEFAULT_GOAL := help

API_URL ?= http://localhost:8080
API_KEY ?= $(shell ./scripts/resolve_api_key.sh)

RAG_GOLD ?= data/golden_set.jsonl
RAG_K ?= 5
RAG_REPORT ?= artifacts/rag_eval/report.json

.PHONY: help
help: ## Show targets
> @awk -F':|##' '/^[a-zA-Z0-9_.-]+:.*##/{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$NF}' $(MAKEFILE_LIST)

.PHONY: smoke
smoke: ## Run API smoke test using /mnt/data/.api_key if present
> API_URL="$(API_URL)" API_KEY="$(API_KEY)" bash tests/integration_smoke.sh

.PHONY: ci-local
ci-local: smoke ## Alias to smoke for local CI

.PHONY: rag-gold-init
rag-gold-init: ## Seed a tiny golden set if missing
> mkdir -p data
> test -s $(RAG_GOLD) || { \
>   echo '{"query":"hello","answer_doc":"docA"}' > $(RAG_GOLD); \
>   echo '{"query":"world","answer_doc":"docB"}' >> $(RAG_GOLD); \
>   echo "Seeded $(RAG_GOLD)"; }

.PHONY: rag-eval
rag-eval: ## Run retrieval eval and write report
> mkdir -p $(dir $(RAG_REPORT))
> $(PY) -m app.rag_eval --gold $(RAG_GOLD) --k $(RAG_K) --report $(RAG_REPORT)
> echo "Wrote $(RAG_REPORT)"

.PHONY: otel-validate
otel-validate: ## Rebuild API and assert OTel headers + spans
> API_URL="$(API_URL)" bash scripts/validate_otel.sh

.PHONY: restart-all
restart-all: ## Rebuild and restart all compose services
> docker compose up -d --build

.PHONY: up-api
up-api: ## Build and start API service only
> docker compose up -d --build api

.PHONY: hardening-validate
hardening-validate: ## Assert request size limit returns 413 with JSON error
> API_URL="$(API_URL)" MACS_MAX_BODY_BYTES="$(MACS_MAX_BODY_BYTES)" bash scripts/validate_hardening.sh

.PHONY: flyway-repair
flyway-repair: ## Repair Flyway schema history via docker compose
> ./scripts/flyway_repair.sh

.PHONY: flyway-migrate
flyway-migrate: ## Run Flyway migrations via docker compose
> ./scripts/flyway_migrate.sh

.PHONY: memory-ingest
memory-ingest: ## Bootstrap existing repo files into workspace memory
> ./tools/memory_ingest_repo.py --root ./workspace

.PHONY: factory-validate
factory-validate: ## 413 check via factory-wrapped ASGI limiter
> API_URL="$(API_URL)" MACS_MAX_BODY_BYTES="$(MACS_MAX_BODY_BYTES)" bash scripts/validate_factory_and_limit.sh
