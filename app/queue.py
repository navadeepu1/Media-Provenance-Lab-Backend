"""Durable queue boundary.

Inline mode remains the default for the offline prototype. RQ mode requires a
Redis URL and a separately started worker; it is never silently downgraded.
"""

from __future__ import annotations

from typing import Callable

from .config import settings


class QueueUnavailable(RuntimeError):
    """The configured queue backend cannot accept work."""


def status() -> str:
    if settings.queue_backend == "inline":
        return "inline"
    if settings.queue_backend == "rq":
        return "rq_configured" if settings.redis_url else "not_configured"
    return "invalid"


def enqueue(job_id: str, runner: Callable[[], object]) -> str:
    if settings.queue_backend == "inline":
        return "inline"
    if settings.queue_backend != "rq" or not settings.redis_url:
        raise QueueUnavailable("RQ requires QUEUE_BACKEND=rq and REDIS_URL.")
    try:
        from redis import Redis
        from rq import Queue
    except ImportError as exc:
        raise QueueUnavailable("Install redis and rq to use the RQ backend.") from exc
    Queue(connection=Redis.from_url(settings.redis_url)).enqueue(runner, job_id=job_id)
    return "rq"
