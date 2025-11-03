#!/usr/bin/env sh
set -e

# 1) Ensure a project .env exists with in-network DSNs
touch .env
upsert() { k="$1"; v="$2"; if grep -qE "^$k=" .env; then sed -i "s|^$k=.*|$k=$v|" .env; else echo "$k=$v" >> .env; fi; }
upsert DATABASE_URL "postgresql+asyncpg://agent:agent@postgres:5432/agent"
upsert OLLAMA_URL "http://ollama:11434"
# If your API needs it for auth, uncomment and set your real key:
# upsert API_KEY "dev-your-key"

echo ">> .env now contains:"
grep -E '^(DATABASE_URL|OLLAMA_URL|API_KEY)=' .env || true

# 2) Overlay to force env_file for runner and api, and map variables through
cat > docker-compose.envfix.yml <<'YML'
services:
  runner:
    env_file:
      - .env
    environment:
      DATABASE_URL: ${DATABASE_URL}
      OLLAMA_URL: ${OLLAMA_URL}
  api:
    env_file:
      - .env
YML

# 3) Merge overlay into a single compose file (keeps your one-file setup)
docker compose -f docker-compose.yml -f docker-compose.envfix.yml config > docker-compose.merged.yml
mv docker-compose.merged.yml docker-compose.yml
rm -f docker-compose.envfix.yml

# 4) Restart runner (and api just in case) so they re-read .env
docker compose up -d --build runner api

# 5) Prove the envs are present inside runner
echo ">> Runner env values:"
docker compose exec -T runner sh -lc 'echo "DATABASE_URL=$DATABASE_URL"; echo "OLLAMA_URL=$OLLAMA_URL"'

echo "All set."
