# Production architecture status

The application now has explicit boundaries for production services while
retaining an offline profile:

| Concern | Local profile | Production requirement |
|---|---|---|
| Database | SQLite | PostgreSQL with managed migrations and backups |
| Queue | In-process inline task | Redis + RQ worker started separately |
| Artifacts | Local filesystem | Private S3-compatible bucket with lifecycle rules |
| Authentication | Disabled | OIDC/OAuth2 and report ownership checks |
| Rate limiting | Process-local memory | Redis-backed distributed limiter |
| Authentication | Disabled | OIDC/OAuth2 and report ownership checks |
| Audit | SQLite audit table | Restricted, retained, exported operator audit log |
| Health | `/api/v1/health`, `/api/v1/ready` | Service checks plus external dependency probes |

`QUEUE_BACKEND=rq` requires `REDIS_URL` and the `redis`/`rq` packages. The
current web process does not silently fall back to inline execution when RQ is
selected. A worker entrypoint and deployment-specific process definition are
still required before production use.

`DATABASE_URL` accepts a SQLAlchemy PostgreSQL URL, but production must use
Alembic migrations rather than `create_all`. `STORAGE_BACKEND=s3` is an
explicit not-configured state until private bucket credentials and an
S3-compatible implementation are supplied; local storage is not suitable for
multi-instance deployment.

The local review workflow, report deletion endpoint, retention cleanup, and
audit table are functional. They are not an authorization system. Do not expose
the local profile publicly: authentication, ownership, tenant isolation,
distributed rate limiting, backup deletion, and privacy-request verification
remain deployment gates.

In `APP_ENV=production`, `/api/v1/ready` is intentionally false unless the
database is reachable, RQ/Redis is configured, S3 storage is selected, and OIDC
authentication is enabled. This prevents a local profile from being mistaken
for a production deployment.
