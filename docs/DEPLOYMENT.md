# Deployment

Render's free native Python service is configured in `render.yaml`. The service has ephemeral local storage and may spin down after inactivity, so a cold request can take up to a minute. Startup creates the SQLite schema and marks queued/running jobs as interrupted. An external uptime check may call `/api/v1/health`, subject to that provider's terms. Record the observed cold-start time, memory, and sample latency here after deployment.

For a browser hosted on another origin, set `CORS_ORIGINS` to a comma-separated allowlist. `RATE_LIMIT_WINDOW_SECONDS` and `RATE_LIMIT_MAX_REQUESTS` control the in-memory per-IP limit on analysis requests; use a shared proxy or rate-limit service if the deployment scales beyond one process.

## Local smoke baseline

The production-like local server was smoke-tested on 2026-11-01 with `scripts/smoke_test.py`. The final warm health latency was 21.83 ms, synthetic sample analysis latency was 8,455.24 ms, and peak RSS across the server process tree was 1,284.50 MB with the local detector loaded. The report completed with tier `NO_SIGNALS`. These are local baseline values, not Render measurements; rerun the same command after deployment and replace this section with the observed Render cold-start, memory, and latency values.
