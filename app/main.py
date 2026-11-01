import asyncio
import html
import io
import logging
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Annotated

from fastapi import FastAPI, File, Header, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image

from . import fixtures, known_items, media, video
from . import c2pa
from .analysis import analyze_bytes
from .config import settings
from .db import (
    cleanup_expired,
    create_job,
    init_db,
    job_dict,
    load_report,
    report_status,
    recover_interrupted_jobs,
    save_report,
    update_job,
)
from .detector import get_detector
from .schemas import Report, Sample

app = FastAPI(title="Media Provenance Lab", docs_url=None, redoc_url=None)
if settings.cors_origins.strip():
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Admin-Key"],
    )

_startup_time = time.time()
_rate_limit_lock = Lock()
_rate_limit_hits: dict[str, deque[float]] = defaultdict(deque)
_cleanup_task: asyncio.Task | None = None
logger = logging.getLogger(__name__)


def error(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message, "details": []}}, status_code=status)


@app.exception_handler(media.UploadRejected)
async def upload_rejected(request: Request, exc: media.UploadRejected) -> JSONResponse:
    return error(exc.code, exc.message, exc.status)


@app.middleware("http")
async def security_headers(request, call_next):
    request_id = secrets.token_hex(16)
    is_analysis_request = (
        request.url.path == "/api/v1/analyze"
        or request.url.path.startswith("/api/v1/samples/")
            and request.url.path.endswith("/analyze")
    )
    if request.method == "POST" and is_analysis_request:
        now = time.monotonic()
        client = request.client.host if request.client else "unknown"
        with _rate_limit_lock:
            hits = _rate_limit_hits[client]
            cutoff = now - settings.rate_limit_window_seconds
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= settings.rate_limit_max_requests:
                response = error("rate_limited", "Too many analysis requests. Please try again later.", 429)
                response.headers["Retry-After"] = str(settings.rate_limit_window_seconds)
                response.headers["X-Request-ID"] = request_id
                return response
            hits.append(now)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path == "/":
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; script-src 'self'; style-src 'self'; "
            "img-src 'self' blob:; connect-src 'self'; base-uri 'none'; form-action 'self'"
        )
    elif request.url.path.startswith("/api/"):
        response.headers["Content-Security-Policy"] = "default-src 'none'"
    return response


samples = [
    Sample(id="clean", title="Clean photo", description="Synthetic clean scene."),
    Sample(id="forwarded", title="Forwarded photo", description="Synthetic re-encoded scene."),
    Sample(id="spliced", title="Spliced photo", description="Synthetic composite scene."),
    Sample(id="copy-moved", title="Copy-moved photo", description="Synthetic duplicated patch."),
    Sample(id="known-item", title="Known reviewed item", description="Synthetic seeded reference item."),
    Sample(id="known-forwarded", title="Forwarded known item", description="Synthetic known item copy."),
    Sample(id="short-video", title="Short edited video", description="Synthetic short media sample."),
]
sample_bytes: dict[str, bytes] = {}


@app.on_event("startup")
async def startup() -> None:
    global _cleanup_task, _startup_time
    _startup_time = time.time()
    settings.data_dir.mkdir(exist_ok=True)
    settings.uploads_dir.mkdir(exist_ok=True)
    settings.derived_dir.mkdir(exist_ok=True)
    init_db()
    recover_interrupted_jobs()
    if not sample_bytes:
        sample_bytes.update(fixtures.sample_images())
    from PIL import Image
    import io
    known_items.seed(
        "known-clean-scene",
        "Known clean synthetic scene",
        "Reference image used to demonstrate perceptual matching.",
        Image.open(io.BytesIO(sample_bytes["known-item"])),
    )
    _cleanup_task = asyncio.create_task(_cleanup_loop())


async def _cleanup_loop() -> None:
    while True:
        try:
            await asyncio.sleep(max(0.01, float(settings.cleanup_interval_seconds)))
            await asyncio.to_thread(cleanup_expired)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Scheduled expired-data cleanup failed")


@app.on_event("shutdown")
async def shutdown() -> None:
    if _cleanup_task:
        _cleanup_task.cancel()
        await asyncio.gather(_cleanup_task, return_exceptions=True)


async def run_job(job_id: str, raw: bytes, demo: bool) -> None:
    try:
        for module in ("ingest", "provenance", "pixel forensics", "fusion", "explanation"):
            current = job_dict(job_id) or {"progress": 0}
            update_job(job_id, current_module=module, progress=min(90, current["progress"] + 18))
            await asyncio.sleep(0)
        report = await asyncio.to_thread(analyze_bytes, raw, demo=demo)
        save_report(report.model_dump(), job_id)
        update_job(job_id, status="done", progress=100, report_id=report.report_id,
                   finished_at=datetime.now(timezone.utc))
    except ValueError as exc:
        update_job(job_id, status="failed", error_code="validation_error",
                   error_message=str(exc), finished_at=datetime.now(timezone.utc))
    except Exception:
        update_job(job_id, status="failed", error_code="internal_error",
                   finished_at=datetime.now(timezone.utc))


async def begin(raw: bytes, demo: bool = False) -> dict:
    job_id = secrets.token_urlsafe(18)
    path = settings.uploads_dir / f"{job_id}.bin"
    path.write_bytes(raw)
    create_job(job_id, path, demo)
    update_job(job_id, status="running")
    asyncio.create_task(run_job(job_id, raw, demo))
    return {"job_id": job_id, "status_url": f"/api/v1/jobs/{job_id}", "status": "queued"}


@app.get("/api/v1/health")
async def health() -> dict:
    detector = get_detector()
    return {"database": "ok",
            "detector": detector.status if detector else "disabled",
            "c2pa": c2pa.capability(),
            "explainer_provider": settings.ai_provider,
            "pipeline_version": "1.0.0",
            "last_startup": _startup_time}


@app.get("/api/v1/samples")
async def get_samples() -> list[Sample]:
    return samples


async def _read_upload(file: UploadFile) -> bytes:
    """Read the upload in chunks. This is a helper, not a route."""
    limit = max(settings.max_image_bytes, settings.max_video_bytes)
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(1024 * 1024):
        total += len(chunk)
        if total > limit:
            raise media.UploadRejected("file_too_large", "The file is larger than the allowed limit.", 413)
        chunks.append(chunk)
    return b"".join(chunks)


@app.post("/api/v1/analyze", status_code=202)
async def analyze(file: Annotated[UploadFile, File(...)]) -> dict:
    raw = await _read_upload(file)
    media_type = media.sniff_media_type(raw)
    if media_type is None:
        raise media.UploadRejected("invalid_file_type", "Upload a JPEG, PNG, WebP, or MP4 file.", 415)
    media.check_size(raw, media_type)
    try:
        if media_type == "image":
            media.check_image_header(raw)
        else:
            await asyncio.to_thread(video.validate_bytes, raw)
    except video.VideoError as exc:
        raise media.UploadRejected("validation_error", str(exc), 422) from exc
    return await begin(raw)


@app.post("/api/v1/samples/{sample_id}/analyze", status_code=202)
async def analyze_sample(sample_id: str) -> dict:
    if sample_id not in sample_bytes:
        return error("not_found", "Sample not found.", 404)
    return await begin(sample_bytes[sample_id], demo=True)


@app.get("/api/v1/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    job = job_dict(job_id)
    if not job:
        return error("not_found", "Job not found.", 404)
    job["job_id"] = job.pop("id")
    return job


@app.get("/api/v1/reports/{report_id}")
async def get_report(report_id: str) -> Report:
    payload = load_report(report_id)
    if not payload:
        status = report_status(report_id)
        if status == "expired":
            return error("expired", "This report has expired.", 410)
        return error("not_found", "Report not found.", 404)
    return Report.model_validate(payload)


@app.get("/api/v1/reports/{report_id}/heatmaps/{name}")
async def get_heatmap(report_id: str, name: str) -> Response:
    payload = load_report(report_id)
    report = Report.model_validate(payload) if payload else None
    if not report:
        status = report_status(report_id)
        if status == "expired":
            return error("expired", "This report has expired.", 410)
        return error("not_found", "Report not found.", 404)
    if "/" in name or "\\" in name or name not in {h["name"] for h in report.heatmaps}:
        return error("not_found", "Heatmap not found.", 404)
    path = settings.derived_dir / name
    if not path.is_file():
        return error("expired", "This heatmap has expired.", 410)
    return Response(path.read_bytes(), media_type="image/png")


@app.get("/api/v1/reports/{report_id}/export")
async def export_report(report_id: str) -> Response:
    payload = load_report(report_id)
    report = Report.model_validate(payload) if payload else None
    if not report:
        status = report_status(report_id)
        if status == "expired":
            return error("expired", "This report has expired.", 410)
        return error("not_found", "Report not found.", 404)
    rows = "".join(
        f"<tr><td>{html.escape(s.name)}</td><td>{s.strength}</td><td>{s.score}</td>"
        f"<td>{html.escape(s.reason or '')}</td></tr>"
        for s in report.signals
    )
    body = f"""<!doctype html><meta charset="utf-8"><title>Media Provenance Report</title>
<style>body{{font:16px sans-serif;max-width:900px;margin:2rem auto}}th,td{{padding:.5rem;border:1px solid #ccc}}</style>
<h1>Evidence report</h1><h2>{report.tier} ({report.applied_rule})</h2><p>{html.escape(report.explanation)}</p>
<table><tr><th>Module</th><th>Strength</th><th>Score</th><th>Reason</th></tr>{rows}</table>"""
    return Response(body, media_type="text/html",
                    headers={"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'"})


@app.get("/api/v1/methodology")
async def methodology() -> dict:
    return {"rules": {"R1": "Two strong families", "R2": "At least one weak or strong family",
                      "R3": "Fewer than two determined families or quality gate failure",
                      "R4": "At least two determined families and all none"},
            "thresholds": {"strong": 0.70, "weak": 0.35}, "metrics": {},
            "limitations": ["Detector weights are not bundled.", "C2PA is not checked in this deployment."]}


@app.post("/api/v1/admin/cleanup")
async def admin_cleanup(x_admin_key: Annotated[str | None, Header()] = None) -> dict:
    if not settings.admin_api_key:
        return error("service_unavailable", "Cleanup is not configured.", 503)
    if not x_admin_key or not secrets.compare_digest(x_admin_key, settings.admin_api_key):
        return error("unauthorized", "The admin key is not valid.", 401)
    return await asyncio.to_thread(cleanup_expired)


@app.get("/")
async def index() -> HTMLResponse:
    return HTMLResponse((Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8"))


app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")