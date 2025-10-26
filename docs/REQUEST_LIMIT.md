# Request size limit
- Enforced at ASGI boundary (BodySizeLimitASGI) via `create_app()` factory.
- Configure with `MACS_MAX_BODY_BYTES` (bytes). Default: 10,485,760 (10 MiB).
- Dev: `docker-compose.local.asgilimit.yml` runs `uvicorn --factory app.main:create_app`.
- Validate: `API_URL=http://localhost:8080 bash scripts/validate_factory_and_limit.sh`
