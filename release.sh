#!/usr/bin/env bash
set -Eeuo pipefail

# --- Config ---
BUMP="${BUMP:-minor}"              # patch | minor | major
NEW_VERSION="${NEW_VERSION:-}"     # e.g. v3.4.0 (overrides BUMP)
SIGN="${SIGN:-0}"                  # 1 = gpg-sign tag if you have GPG set up

# --- Ensure we are in a git repo ---
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || {
  echo "Not a git repository. Run this from your repo root."; exit 1; }

# --- Derive next version ---
latest_tag="$(git tag --list 'v*' --sort=-v:refname | head -n1 || true)"
base="${latest_tag#v}"
if [ -z "$base" ]; then base="0.0.0"; fi

if [ -n "$NEW_VERSION" ]; then
  tag="${NEW_VERSION#v}"; tag="v${tag}"
else
  IFS=. read -r MA MI PA <<< "${base}"
  MA=${MA:-0}; MI=${MI:-0}; PA=${PA:-0}
  case "$BUMP" in
    patch) PA=$((PA+1));;
    minor) MI=$((MI+1)); PA=0;;
    major) MA=$((MA+1)); MI=0; PA=0;;
    *) echo "Unknown BUMP=$BUMP (use patch|minor|major)"; exit 2;;
  esac
  tag="v${MA}.${MI}.${PA}"
fi
plain="${tag#v}"

# --- Write/refresh VERSION file (unprefixed, e.g. 3.4.0) ---
echo "${plain}" > VERSION

# --- Stage the known files (safe; won't add .env) ---
git add -A -- \
  docker-compose.yml \
  README.md \
  VERSION 2>/dev/null || true

# If nothing staged, do not fail; still allow tagging
if git diff --cached --quiet; then
  echo "No staged changes detected; proceeding to tag ${tag} only."
else
  # --- Commit message (conventional) ---
  cat > .git/COMMIT_MSG <<'EOF'
feat(stack): single-file compose + Prometheus & Grafana; docs quickstart

- Consolidate runtime into ONE docker-compose.yml:
  - API (host 8080, overridable), Postgres (host 55432), Ollama (GPU, internal-only),
    Prometheus (host 39090), Grafana (host 33000).
- Prevent 11434 conflicts by keeping Ollama internal; API talks via service DNS.
- Provision Prometheus scrape for API and Grafana datasource.
- README: quickstart, health checks, URLs, port overrides, GPU notes, troubleshooting.
- Add VERSION file for SemVer tracking; require API_KEY via .env for startup.
EOF
  git commit -F .git/COMMIT_MSG
fi

# --- Tag message (annotated) ---
cat > .git/TAG_MSG <<EOF
${tag} — single-file stack + dashboards; README quickstart

Highlights:
- Single docker-compose.yml (API + Postgres + Ollama GPU + Prometheus + Grafana).
- Internal-only Ollama (no 11434 host bind) to avoid port conflicts.
- Defaults: API 8080, Postgres 55432, Prometheus 39090, Grafana 33000 (all overridable).
- Auto-provisioned Prom scrape & Grafana datasource.
- README with commands, URLs, port overrides, GPU notes, troubleshooting.

Changed files:
- docker-compose.yml
- README.md
- VERSION
EOF

if [ "${SIGN}" = "1" ]; then
  git tag -s "${tag}" -F .git/TAG_MSG
else
  git tag -a "${tag}" -F .git/TAG_MSG
fi

branch="$(git rev-parse --abbrev-ref HEAD || true)"
echo
echo "✅ Created ${tag} on branch ${branch}"
echo
echo "Next steps:"
echo "  git push origin ${branch:-main}"
echo "  git push origin ${tag}"
