# OpenTelemetry — Quick Check
- Rebuild & run: `docker compose up -d --build api`
- Validate (headers + spans): `make otel-validate` or `API_URL=http://localhost:8080 bash scripts/validate_otel.sh`
- Pass = response has `x-otel-enabled: 1` and a 32-hex `x-trace-id`; API logs print spans.
