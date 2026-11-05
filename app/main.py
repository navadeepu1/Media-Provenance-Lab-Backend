import asyncio
import html
import io
import json
import logging
import secrets
import time
from contextlib import asynccontextmanager
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Annotated

from fastapi import FastAPI, File, Form, Header, Request, UploadFile
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
    delete_report,
    expire_overdue_jobs,
    healthcheck,
    init_db,
    job_cancel_requested,
    job_dict,
    load_report,
    report_status,
    recover_interrupted_jobs,
    save_report,
    request_job_cancellation,
    update_job,
)
from .detector import get_detector
from . import forensics
from .privacy import audit, create_review, recent_events, update_review
from .queue import status as queue_status
from .storage import backend_status, put_bytes, secure_delete
from .schemas import Report, Sample
from .forensics.models import (
    BookmarkCreate, CaseCreate, CaseStatusChange, Finding, FindingStatusChange,
    NoteCreate, NormalizedEvent, TagCreate,
)
from .forensics.parsers import parse_firefox, parse_json_csv, parse_linux, parse_web, parse_windows_xml
from .forensics.persistence import (
    change_case_status, create_bookmark, create_case as create_v2_case,
    create_note, create_tag, delete_evidence, ensure_case, get_case, get_evidence,
    list_bookmarks, list_cases as list_v2_cases, list_evidence, list_notes,
    list_tags, load_events, load_findings, save_evidence, save_events,
    save_findings, timeline_filtered, update_finding_status,
)
from .forensics.rules import run_all
from .forensics.incidents import group_incidents, match_sequences
from .forensics.persistence import load_incidents, save_incidents
from .forensics.custody import append as append_custody, verify as verify_custody_v2

logger = logging.getLogger(__name__)


def _authenticated_user(authorization: str | None) -> str | None:
    if settings.authentication_backend == "none":
        return "local-user"
    if settings.authentication_backend != "local_bearer":
        return None
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[7:].strip()
    for entry in settings.auth_tokens.split(","):
        if ":" not in entry:
            continue
        username, expected = entry.split(":", 1)
        if secrets.compare_digest(token, expected):
            return username.strip() or None
    return None


def _require_case_access(case_id: str, authorization: str | None) -> tuple[str | None, JSONResponse | None]:
    user = _authenticated_user(authorization)
    if not user:
        return None, error("unauthorized", "Authentication is required.", 401)
    if not forensics.owns_case(case_id, user):
        return None, error("forbidden", "You do not have access to this case.", 403)
    return user, None


def _log_event(event: str, **fields: object) -> None:
    logger.info(json.dumps({"event": event, "timestamp": datetime.now(timezone.utc).isoformat(),
                            **fields}, default=str, sort_keys=True))


_cleanup_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _cleanup_task, _startup_time
    _startup_time = time.time()
    settings.data_dir.mkdir(exist_ok=True)
    settings.uploads_dir.mkdir(exist_ok=True)
    settings.derived_dir.mkdir(exist_ok=True)
    init_db()
    recovered = recover_interrupted_jobs()
    if recovered:
        _log_event("jobs_recovered", count=recovered)
    if not sample_bytes:
        sample_bytes.update(fixtures.sample_images())
    known_items.seed(
        "known-clean-scene",
        "Known clean synthetic scene",
        "Reference image used to demonstrate perceptual matching.",
        Image.open(io.BytesIO(sample_bytes["known-item"])),
    )
    _cleanup_task = asyncio.create_task(_cleanup_loop())
    try:
        yield
    finally:
        if _cleanup_task:
            _cleanup_task.cancel()
            await asyncio.gather(_cleanup_task, return_exceptions=True)


app = FastAPI(title="Media Provenance Lab", docs_url=None, redoc_url=None, lifespan=lifespan)
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


async def _cleanup_loop() -> None:
    while True:
        try:
            await asyncio.sleep(max(0.01, float(settings.cleanup_interval_seconds)))
            overdue = await asyncio.to_thread(expire_overdue_jobs)
            cleanup = await asyncio.to_thread(cleanup_expired)
            if overdue or any(cleanup.values()):
                _log_event("maintenance", overdue_jobs=overdue, **cleanup)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Scheduled expired-data cleanup failed")


async def run_job(job_id: str, raw: bytes, demo: bool) -> None:
    started = time.perf_counter()
    job = job_dict(job_id)
    deadline = job.get("deadline_at") if job else None
    try:
        for module in ("ingest", "provenance", "pixel forensics", "fusion", "explanation"):
            current = job_dict(job_id) or {"progress": 0}
            update_job(job_id, current_module=module, progress=min(90, current["progress"] + 18))
            await asyncio.sleep(0)
        if job_cancel_requested(job_id):
            raise asyncio.CancelledError
        remaining = (deadline - datetime.now(timezone.utc).replace(tzinfo=None)).total_seconds() if deadline else settings.job_budget_seconds
        report = await asyncio.wait_for(
            asyncio.to_thread(analyze_bytes, raw, demo=demo),
            timeout=max(0.01, remaining),
        )
        if job_cancel_requested(job_id):
            raise asyncio.CancelledError
        save_report(report.model_dump(), job_id)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        update_job(job_id, status="done", progress=100, report_id=report.report_id,
                   duration_ms=duration_ms, finished_at=datetime.now(timezone.utc))
        _log_event("analysis_completed", job_id=job_id, report_id=report.report_id,
                   duration_ms=duration_ms, tier=report.tier)
    except asyncio.TimeoutError:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        update_job(job_id, status="failed", error_code="timeout",
                   error_message="Analysis exceeded its time budget.", duration_ms=duration_ms,
                   finished_at=datetime.now(timezone.utc))
        _log_event("analysis_timeout", job_id=job_id, duration_ms=duration_ms)
    except asyncio.CancelledError:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        update_job(job_id, status="failed", error_code="cancelled",
                   error_message="Analysis was cancelled before completion.", duration_ms=duration_ms,
                   finished_at=datetime.now(timezone.utc))
        _log_event("analysis_cancelled", job_id=job_id, duration_ms=duration_ms)
    except ValueError as exc:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        update_job(job_id, status="failed", error_code="validation_error",
                   error_message=str(exc), duration_ms=duration_ms, finished_at=datetime.now(timezone.utc))
        _log_event("analysis_rejected", job_id=job_id, duration_ms=duration_ms, reason=str(exc))
    except Exception:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        update_job(job_id, status="failed", error_code="internal_error",
                   error_message="The analysis failed unexpectedly.", duration_ms=duration_ms,
                   finished_at=datetime.now(timezone.utc))
        logger.exception("analysis_failed job_id=%s", job_id)


async def begin(raw: bytes, demo: bool = False) -> dict:
    job_id = secrets.token_urlsafe(18)
    path = settings.uploads_dir / f"{job_id}.bin"
    path.write_bytes(raw)
    deadline = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=settings.job_budget_seconds)
    create_job(job_id, path, demo, deadline)
    update_job(job_id, status="running", started_at=datetime.now(timezone.utc))
    _log_event("analysis_queued", job_id=job_id, demo=demo, bytes=len(raw),
               deadline_at=deadline.isoformat())
    asyncio.create_task(run_job(job_id, raw, demo))
    return {"job_id": job_id, "status_url": f"/api/v1/jobs/{job_id}", "status": "queued"}


@app.get("/api/v1/health")
async def health() -> dict:
    detector = get_detector()
    return {"database": healthcheck(),
            "queue": queue_status(),
            "storage": backend_status(),
            "detector": detector.status if detector else "disabled",
            "c2pa": c2pa.capability(),
            "explainer_provider": settings.ai_provider,
            "pipeline_version": "1.0.0",
            "last_startup": _startup_time}


@app.get("/api/v1/ready")
async def readiness() -> dict:
    checks = {
        "database": healthcheck(),
        "queue": queue_status(),
        "storage": backend_status(),
        "authentication": settings.authentication_backend,
    }
    if settings.app_env == "production":
        ready = checks == {
            "database": "ok", "queue": "rq_configured", "storage": "s3",
            "authentication": "oidc",
        }
    else:
        ready = all(value in {"ok", "inline", "local", "none"} for value in checks.values())
    return {"ready": ready, "checks": checks}


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
    if not file.filename or not file.filename.strip():
        raise media.UploadRejected(
            "missing_file", "Select a media file before starting analysis.", 422
        )
    raw = await _read_upload(file)
    if not raw:
        raise media.UploadRejected(
            "empty_file", "The selected media file is empty.", 422
        )
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


@app.post("/api/v1/jobs/{job_id}/cancel")
async def cancel_job(job_id: str) -> dict:
    if not request_job_cancellation(job_id):
        job = job_dict(job_id)
        if not job:
            return error("not_found", "Job not found.", 404)
        return error("not_cancellable", "This job is no longer running.", 409)
    _log_event("analysis_cancel_requested", job_id=job_id)
    return {"job_id": job_id, "status": "cancellation_requested"}


@app.get("/api/v1/reports/{report_id}")
async def get_report(report_id: str) -> Report:
    payload = load_report(report_id)
    if not payload:
        status = report_status(report_id)
        if status == "expired":
            return error("expired", "This report has expired.", 410)
        return error("not_found", "Report not found.", 404)
    return Report.model_validate(payload)


@app.delete("/api/v1/reports/{report_id}")
async def delete_report(report_id: str) -> dict:
    if report_status(report_id) == "missing":
        return error("not_found", "Report not found.", 404)
    deleted = await asyncio.to_thread(_delete_report_data, report_id)
    audit("report_deleted", subject_id=report_id)
    return {"report_id": report_id, "deleted": deleted}


def _delete_report_data(report_id: str) -> bool:
    return delete_report(report_id)


@app.post("/api/v1/reports/{report_id}/reviews")
async def create_report_review(report_id: str) -> dict:
    if not load_report(report_id):
        return error("not_found", "Report not found.", 404)
    return await asyncio.to_thread(create_review, report_id)


@app.patch("/api/v1/reviews/{review_id}")
async def patch_review(review_id: int, payload: dict[str, str | None]) -> dict:
    status_value = payload.get("status")
    if status_value not in {"queued", "in_review", "completed"}:
        return error("invalid_review_status", "Review status is invalid.", 422)
    result = await asyncio.to_thread(
        update_review, review_id, status_value, payload.get("decision"), payload.get("notes")
    )
    if result is None:
        return error("not_found", "Review task not found.", 404)
    return result


@app.post("/api/v1/cases", status_code=201)
async def create_forensic_case(payload: dict[str, str | None],
                               authorization: Annotated[str | None, Header()] = None) -> dict:
    user = _authenticated_user(authorization)
    if not user:
        return error("unauthorized", "Authentication is required.", 401)
    try:
        return await asyncio.to_thread(
            forensics.create_case, payload.get("title", ""), payload.get("description") or "", user
        )
    except ValueError as exc:
        return error("invalid_case", str(exc), 422)


@app.get("/api/v1/cases")
async def get_forensic_cases(authorization: Annotated[str | None, Header()] = None) -> dict:
    user = _authenticated_user(authorization)
    if not user:
        return error("unauthorized", "Authentication is required.", 401)
    cases = await asyncio.to_thread(forensics.list_cases)
    return {"cases": [case for case in cases if case["owner_id"] == user]}


@app.post("/api/v1/cases/{case_id}/evidence", status_code=201)
async def ingest_forensic_evidence(
    case_id: str,
    file: UploadFile = File(...),
    kind: str = Form(...),
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    _, denial = _require_case_access(case_id, authorization)
    if denial:
        return denial
    raw = await file.read()
    try:
        result = await asyncio.to_thread(
            forensics.ingest_evidence, case_id, file.filename or "evidence", kind, raw
        )
        return result
    except ValueError as exc:
        return error("invalid_evidence", str(exc), 422)


@app.get("/api/v1/cases/{case_id}/timeline")
async def get_forensic_timeline(case_id: str, q: str = "",
                                authorization: Annotated[str | None, Header()] = None) -> dict:
    _, denial = _require_case_access(case_id, authorization)
    if denial:
        return denial
    return {"events": await asyncio.to_thread(forensics.timeline, case_id, q)}


@app.post("/api/v1/cases/{case_id}/assistant")
async def ask_forensic_assistant(case_id: str, payload: dict[str, str | None],
                                 authorization: Annotated[str | None, Header()] = None) -> dict:
    _, denial = _require_case_access(case_id, authorization)
    if denial:
        return denial
    try:
        return await asyncio.to_thread(
            forensics.assistant_answer, case_id, payload.get("question") or ""
        )
    except ValueError as exc:
        return error("invalid_question", str(exc), 422)


@app.get("/api/v1/cases/{case_id}/custody/verify")
async def verify_forensic_custody(case_id: str,
                                  authorization: Annotated[str | None, Header()] = None) -> dict:
    _, denial = _require_case_access(case_id, authorization)
    if denial:
        return denial
    return await asyncio.to_thread(forensics.verify_custody, case_id)


@app.post("/api/v1/cases/{case_id}/custody/anchor")
async def anchor_forensic_custody(case_id: str,
                                  authorization: Annotated[str | None, Header()] = None) -> dict:
    _, denial = _require_case_access(case_id, authorization)
    if denial:
        return denial
    return await asyncio.to_thread(forensics.anchor_custody, case_id)


@app.get("/api/v1/cases/{case_id}/findings")
async def get_forensic_findings(case_id: str,
                                authorization: Annotated[str | None, Header()] = None) -> dict:
    _, denial = _require_case_access(case_id, authorization)
    if denial:
        return denial
    return {"findings": await asyncio.to_thread(forensics.suspicious_activity, case_id)}


@app.get("/api/v1/admin/audit")
async def audit_events(x_admin_key: Annotated[str | None, Header()] = None) -> dict:
    if not settings.admin_api_key:
        return error("service_unavailable", "Audit access is not configured.", 503)
    if not x_admin_key or not secrets.compare_digest(x_admin_key, settings.admin_api_key):
        return error("unauthorized", "The admin key is not valid.", 401)
    return {"events": await asyncio.to_thread(recent_events)}


@app.get("/api/v2/health")
async def v2_health() -> dict:
    return {"status": "ok", "api": "v2", "rules": ["R-LOGIN-BURST", "R-OFFHOURS",
                                                       "R-PRIV-ESC", "R-ACCESS-BURST", "R-DELETE-BURST"]}


@app.post("/api/v2/cases/{case_id}/evidence", status_code=201)
async def v2_ingest_evidence(
    case_id: str,
    file: UploadFile = File(...),
    parser: str = Form(...),
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    tenant_id = _authenticated_user(authorization)
    if not tenant_id:
        return error("unauthorized", "Authentication is required.", 401)
    raw = await file.read()
    evidence_id = secrets.token_hex(16)
    await asyncio.to_thread(ensure_case, tenant_id, case_id)
    sha256 = __import__("hashlib").sha256(raw).hexdigest()
    storage_key = await asyncio.to_thread(put_bytes, raw, f"v2/{tenant_id}/{case_id}", evidence_id)
    if parser in {"json", "csv"}:
        events, warnings = await asyncio.to_thread(parse_json_csv, raw, tenant_id, case_id, evidence_id, parser)
    elif parser == "linux_auth":
        events, warnings = await asyncio.to_thread(parse_linux, raw, tenant_id, case_id, evidence_id)
    elif parser == "web_access":
        events, warnings = await asyncio.to_thread(parse_web, raw, tenant_id, case_id, evidence_id)
    elif parser == "windows_xml":
        events, warnings = await asyncio.to_thread(parse_windows_xml, raw, tenant_id, case_id, evidence_id)
    elif parser == "firefox_history":
        events, warnings = await asyncio.to_thread(parse_firefox, raw, tenant_id, case_id, evidence_id)
    else:
        return error("unsupported_parser", "Parser must be json, csv, linux_auth, web_access, windows_xml, or firefox_history.", 422)
    await asyncio.to_thread(save_evidence, tenant_id, case_id, evidence_id,
                            file.filename or evidence_id, len(raw), sha256, parser,
                            storage_key, file.content_type or "application/octet-stream")
    count = await asyncio.to_thread(save_events, events)
    await asyncio.to_thread(append_custody, tenant_id, evidence_id, "ingest",
                            sha256, tenant_id)
    findings_models = run_all(events) + match_sequences(events)
    findings = await asyncio.to_thread(save_findings, findings_models)
    incidents = await asyncio.to_thread(group_incidents, events, findings_models)
    await asyncio.to_thread(save_incidents, incidents, tenant_id, case_id)
    audit("v2_evidence_ingested", subject_id=evidence_id, tenant_id=tenant_id,
          case_id=case_id, parser=parser, event_count=count)
    return {"evidence_id": evidence_id, "parser": parser, "event_count": count,
            "finding_count": findings, "parse_warnings": warnings,
            "sha256": sha256}


@app.post("/api/v2/cases", status_code=201)
async def v2_create_case(
    payload: CaseCreate,
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    tenant_id = _authenticated_user(authorization)
    if not tenant_id:
        return error("unauthorized", "Authentication is required.", 401)
    result = await asyncio.to_thread(create_v2_case, tenant_id, payload.title)
    audit("v2_case_created", subject_id=result["id"], tenant_id=tenant_id)
    return result


@app.get("/api/v2/cases")
async def v2_list_cases(
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    tenant_id = _authenticated_user(authorization)
    if not tenant_id:
        return error("unauthorized", "Authentication is required.", 401)
    return {"cases": await asyncio.to_thread(list_v2_cases, tenant_id)}


@app.get("/api/v2/cases/{case_id}")
async def v2_get_case(
    case_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    tenant_id = _authenticated_user(authorization)
    if not tenant_id:
        return error("unauthorized", "Authentication is required.", 401)
    result = await asyncio.to_thread(get_case, tenant_id, case_id)
    return result or error("not_found", "Case not found.", 404)


@app.patch("/api/v2/cases/{case_id}/status")
async def v2_change_case_status(
    case_id: str,
    payload: CaseStatusChange,
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    tenant_id = _authenticated_user(authorization)
    if not tenant_id:
        return error("unauthorized", "Authentication is required.", 401)
    try:
        result = await asyncio.to_thread(
            change_case_status, tenant_id, case_id, payload.status, payload.reason
        )
    except ValueError as exc:
        return error("invalid_status_transition", str(exc), 422)
    if result is None:
        return error("not_found", "Case not found.", 404)
    audit("v2_case_status_changed", subject_id=case_id, tenant_id=tenant_id,
          status=payload.status)
    return result


@app.get("/api/v2/cases/{case_id}/evidence")
async def v2_list_evidence(
    case_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    tenant_id = _authenticated_user(authorization)
    if not tenant_id:
        return error("unauthorized", "Authentication is required.", 401)
    if not await asyncio.to_thread(get_case, tenant_id, case_id):
        return error("not_found", "Case not found.", 404)
    return {"evidence": await asyncio.to_thread(list_evidence, tenant_id, case_id)}


@app.get("/api/v2/evidence/{evidence_id}")
async def v2_get_evidence(
    evidence_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    tenant_id = _authenticated_user(authorization)
    if not tenant_id:
        return error("unauthorized", "Authentication is required.", 401)
    result = await asyncio.to_thread(get_evidence, tenant_id, evidence_id)
    return result or error("not_found", "Evidence not found.", 404)


@app.delete("/api/v2/evidence/{evidence_id}")
async def v2_delete_evidence(
    evidence_id: str,
    hard: bool = False,
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    user = _authenticated_user(authorization)
    if not user:
        return error("unauthorized", "Authentication is required.", 401)
    if hard and user != "admin":
        return error("forbidden", "Only an administrator can hard-delete evidence.", 403)
    result = await asyncio.to_thread(delete_evidence, user, evidence_id, hard)
    if not result:
        return error("not_found", "Evidence not found.", 404)
    if hard:
        await asyncio.to_thread(secure_delete, result["storage_key"])
    audit("v2_evidence_deleted", subject_id=evidence_id, tenant_id=user, hard=hard)
    return result


@app.post("/api/v2/cases/{case_id}/notes", status_code=201)
async def v2_create_note(
    case_id: str,
    payload: NoteCreate,
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    tenant_id = _authenticated_user(authorization)
    if not tenant_id:
        return error("unauthorized", "Authentication is required.", 401)
    if not await asyncio.to_thread(get_case, tenant_id, case_id):
        return error("not_found", "Case not found.", 404)
    result = await asyncio.to_thread(create_note, tenant_id, case_id, tenant_id, payload.text)
    audit("v2_note_created", subject_id=result["id"], tenant_id=tenant_id, case_id=case_id)
    return result


@app.get("/api/v2/cases/{case_id}/notes")
async def v2_list_notes(
    case_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    tenant_id = _authenticated_user(authorization)
    if not tenant_id:
        return error("unauthorized", "Authentication is required.", 401)
    if not await asyncio.to_thread(get_case, tenant_id, case_id):
        return error("not_found", "Case not found.", 404)
    return {"notes": await asyncio.to_thread(list_notes, tenant_id, case_id)}


@app.post("/api/v2/cases/{case_id}/tags", status_code=201)
async def v2_create_tag(
    case_id: str,
    payload: TagCreate,
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    tenant_id = _authenticated_user(authorization)
    if not tenant_id:
        return error("unauthorized", "Authentication is required.", 401)
    if not await asyncio.to_thread(get_case, tenant_id, case_id):
        return error("not_found", "Case not found.", 404)
    result = await asyncio.to_thread(create_tag, tenant_id, case_id, payload.name)
    audit("v2_case_tagged", subject_id=result["id"], tenant_id=tenant_id, case_id=case_id)
    return result


@app.get("/api/v2/cases/{case_id}/tags")
async def v2_list_tags(
    case_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    tenant_id = _authenticated_user(authorization)
    if not tenant_id:
        return error("unauthorized", "Authentication is required.", 401)
    if not await asyncio.to_thread(get_case, tenant_id, case_id):
        return error("not_found", "Case not found.", 404)
    return {"tags": await asyncio.to_thread(list_tags, tenant_id, case_id)}


@app.post("/api/v2/cases/{case_id}/bookmarks", status_code=201)
async def v2_create_bookmark(
    case_id: str,
    payload: BookmarkCreate,
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    tenant_id = _authenticated_user(authorization)
    if not tenant_id:
        return error("unauthorized", "Authentication is required.", 401)
    try:
        result = await asyncio.to_thread(
            create_bookmark, tenant_id, case_id, payload.event_id, payload.finding_id
        )
    except ValueError as exc:
        return error("invalid_bookmark", str(exc), 422)
    audit("v2_bookmark_created", subject_id=result["id"], tenant_id=tenant_id, case_id=case_id)
    return result


@app.get("/api/v2/cases/{case_id}/bookmarks")
async def v2_list_bookmarks(
    case_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    tenant_id = _authenticated_user(authorization)
    if not tenant_id:
        return error("unauthorized", "Authentication is required.", 401)
    return {"bookmarks": await asyncio.to_thread(list_bookmarks, tenant_id, case_id)}


@app.patch("/api/v2/findings/{finding_id}/status")
async def v2_update_finding_status(
    finding_id: str,
    payload: FindingStatusChange,
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    tenant_id = _authenticated_user(authorization)
    if not tenant_id:
        return error("unauthorized", "Authentication is required.", 401)
    try:
        result = await asyncio.to_thread(
            update_finding_status, tenant_id, finding_id, payload.status, payload.reason
        )
    except ValueError as exc:
        return error("invalid_finding_status", str(exc), 422)
    if result is None:
        return error("not_found", "Finding not found.", 404)
    audit("v2_finding_status_changed", subject_id=finding_id, tenant_id=tenant_id,
          status=payload.status)
    return result


@app.get("/api/v2/cases/{case_id}/timeline")
async def v2_timeline(
    case_id: str,
    actor: str | None = None,
    host: str | None = None,
    source_type: str | None = None,
    action: str | None = None,
    minimum_severity: str | None = None,
    from_time: datetime | None = None,
    to_time: datetime | None = None,
    incident: str | None = None,
    cursor: str | None = None,
    limit: int = 100,
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    tenant_id = _authenticated_user(authorization)
    if not tenant_id:
        return error("unauthorized", "Authentication is required.", 401)
    if not await asyncio.to_thread(get_case, tenant_id, case_id):
        return error("not_found", "Case not found.", 404)
    result = await asyncio.to_thread(
        timeline_filtered, tenant_id, case_id, actor, host, source_type, action,
        minimum_severity, from_time, to_time, incident, cursor, limit
    )
    result["events"] = [event.model_dump(mode="json") for event in result["events"]]
    return result


@app.get("/api/v2/cases/{case_id}/findings")
async def v2_findings(
    case_id: str,
    minimum_severity: str | None = None,
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    tenant_id = _authenticated_user(authorization)
    if not tenant_id:
        return error("unauthorized", "Authentication is required.", 401)
    if not await asyncio.to_thread(get_case, tenant_id, case_id):
        return error("not_found", "Case not found.", 404)
    findings = await asyncio.to_thread(load_findings, tenant_id, case_id)
    order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    minimum = order.get(minimum_severity or "low", 0)
    filtered = [finding for finding in findings if order.get(finding.severity, 0) >= minimum]
    return {"findings": [finding.model_dump(mode="json") for finding in filtered]}


@app.get("/api/v2/cases/{case_id}/incidents")
async def v2_incidents(
    case_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    tenant_id = _authenticated_user(authorization)
    if not tenant_id:
        return error("unauthorized", "Authentication is required.", 401)
    if not await asyncio.to_thread(get_case, tenant_id, case_id):
        return error("not_found", "Case not found.", 404)
    return {"incidents": await asyncio.to_thread(load_incidents, tenant_id, case_id)}


@app.get("/api/v2/evidence/{evidence_id}/custody")
async def v2_custody(
    evidence_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    tenant_id = _authenticated_user(authorization)
    if not tenant_id:
        return error("unauthorized", "Authentication is required.", 401)
    return await asyncio.to_thread(verify_custody_v2, tenant_id, evidence_id)


@app.get("/api/v1/capabilities")
async def capabilities() -> dict:
    return {
        "adaptive_video": {
            "status": "partial",
            "details": "Bounded one-frame-per-second sampling is implemented; adaptive/full-video analysis is not enabled.",
        },
        "audio_sync": {
            "status": "not_configured",
            "details": "Audio extraction and audiovisual synchronization require an approved ffmpeg deployment.",
        },
        "url_ingestion": {
            "status": "not_configured",
            "details": "Direct upload is enabled; URL ingestion is disabled until SSRF controls and provider terms are reviewed.",
        },
        "suspicious_activity": {
            "status": "local",
            "details": "Deterministic findings flag privilege, destructive, authentication-failure, and access activity with event citations.",
        },
        "authentication": {
            "status": settings.authentication_backend,
            "details": "Use AUTHENTICATION_BACKEND=local_bearer and AUTH_TOKENS=username:token pairs for local ownership enforcement; OIDC remains deployment-specific.",
        },
        "custody_anchoring": {
            "status": "local_file",
            "details": "Latest custody hashes can be anchored to a separately retained local file; a trusted third-party timestamp service is not bundled.",
        },
        "c2pa_chain": {
            "status": "partial",
            "details": "Optional C2PA manifest capability/status is reported; signing and full chain visualization are not enabled.",
        },
        "human_review": {
            "status": "local",
            "details": "Review task creation and status updates are available in local mode; authentication and assignment are not enabled.",
        },
        "digital_forensics": {
            "status": "local",
            "details": "Cases, JSON/JSONL, CSV, text-log, and filesystem-metadata ingestion, normalized timelines, cited local queries, and custody verification are enabled.",
        },
        "model_monitoring": {
            "status": "not_configured",
            "details": "Report timing and tier metrics are recorded; drift storage, baselines, and alerting remain to be configured.",
        },
    }


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