#!/usr/bin/env bash
# 10MB max body, 60s timeout as a sane default
exec uvicorn app.main:app --host 0.0.0.0 --port 8080 --timeout-keep-alive 60 --limit-max-request 10485760
