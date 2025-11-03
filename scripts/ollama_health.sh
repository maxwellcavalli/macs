#!/usr/bin/env bash
set -euo pipefail
curl -s http://localhost:8080/v1/ollama/health | jq .
