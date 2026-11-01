"""Run production-like HTTP smoke checks and write measured results as JSON."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import httpx
import psutil


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--pid", type=int, help="Local server PID to measure RSS for")
    parser.add_argument("--output", type=Path, default=Path("smoke-results.json"))
    args = parser.parse_args()

    client = httpx.Client(base_url=args.base_url.rstrip("/"), timeout=args.timeout)
    started = time.perf_counter()
    health = client.get("/api/v1/health")
    health.raise_for_status()
    health_latency_ms = round((time.perf_counter() - started) * 1000, 2)

    samples = client.get("/api/v1/samples")
    samples.raise_for_status()
    sample_id = samples.json()[0]["id"]
    started = time.perf_counter()
    queued = client.post(f"/api/v1/samples/{sample_id}/analyze")
    queued.raise_for_status()
    job = queued.json()
    while True:
        status = client.get(job["status_url"])
        status.raise_for_status()
        payload = status.json()
        if payload["status"] in {"done", "failed"}:
            break
        time.sleep(0.25)
    analysis_latency_ms = round((time.perf_counter() - started) * 1000, 2)
    if payload["status"] != "done":
        raise RuntimeError(f"Smoke analysis failed: {payload}")
    report = client.get(f"/api/v1/reports/{payload['report_id']}")
    report.raise_for_status()
    export = client.get(f"/api/v1/reports/{payload['report_id']}/export")
    export.raise_for_status()

    process_rss_mb = None
    if args.pid:
        processes = [psutil.Process(args.pid), *psutil.Process(args.pid).children(recursive=True)]
        process_rss_mb = round(
            max(process.memory_info().rss for process in processes if process.is_running())
            / 1024
            / 1024,
            2,
        )
    result = {
        "base_url": args.base_url,
        "health_latency_ms": health_latency_ms,
        "analysis_latency_ms": analysis_latency_ms,
        "report_id": payload["report_id"],
        "tier": report.json()["tier"],
        "process_rss_mb": process_rss_mb,
        "health": health.json(),
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
