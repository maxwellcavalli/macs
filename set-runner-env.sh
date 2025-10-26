#!/usr/bin/env sh
set -e
touch .env
upsert() { k="$1"; v="$2"; if grep -qE "^$k=" .env; then sed -i "s|^$k=.*|$k=$v|" .env; else echo "$k=$v" >> .env; fi; }

# Postgres inside the compose network (async driver)
upsert DATABASE_URL "postgresql+asyncpg://agent:agent@postgres:5432/agent"

# Ollama inside the compose network
upsert OLLAMA_URL "http://ollama:11434"

# (Optional) API key if your image needs it for other calls
# upsert API_KEY "dev-your-key"

echo "Updated .env (showing relevant keys):"
grep -E '^(DATABASE_URL|OLLAMA_URL|API_KEY)=' .env || true
