# Deployment

Render's free native Python service is configured in `render.yaml`. The service has ephemeral local storage and may spin down after inactivity, so a cold request can take up to a minute. An external uptime check may call `/api/v1/health`, subject to that provider's terms. Record the observed cold-start time, memory, and sample latency here after deployment.

