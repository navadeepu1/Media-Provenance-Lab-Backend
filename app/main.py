import asyncio
import html
import io
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image

from .analysis import analyze_bytes
from .config import settings
from .db import cleanup_expired, create_job, init_db, job_dict, load_report, recover_interrupted_jobs, save_report, update_job
from .schemas import Report, Sample

app = FastAPI(title="Media Provenance Lab", docs_url=None, redoc_url=None)
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
    settings.data_dir.mkdir(exist_ok=True)
    settings.uploads_dir.mkdir(exist_ok=True)
    settings.derived_dir.mkdir(exist_ok=True)
    init_db()
    recover_interrupted_jobs()
    for sample in samples:
        if sample.id not in sample_bytes:
            image = Image.new("RGB", (640, 480), (50 + len(sample.id) * 7 % 150, 100, 160))
            buf = io.BytesIO()
            image.save(buf, "PNG")
            sample_bytes[sample.id] = buf.getvalue()


def error(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message, "details": []}}, status_code=status)


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
    return {"database": "ok", "detector": "not_loaded", "c2pa": "not_checked",
            "explainer_provider": settings.ai_provider, "pipeline_version": "1.0.0",
            "last_startup": time.time()}


@app.get("/api/v1/samples")
async def get_samples() -> list[Sample]:
    return samples


@app.post("/api/v1/analyze", status_code=202)
async def analyze(file: Annotated[UploadFile, File(...)]) -> dict:
    raw = await file.read(settings.max_video_bytes + 1)
    if len(raw) > settings.max_video_bytes:
        return error("file_too_large", "The file is larger than the allowed limit.", 413)
    if not raw.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"RIFF")):
        return error("invalid_file_type", "Upload a JPEG, PNG, WebP, or MP4 file.", 415)
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
        return error("not_found", "Report not found.", 404)
    return Report.model_validate(payload)


@app.get("/api/v1/reports/{report_id}/heatmaps/{name}")
async def get_heatmap(report_id: str, name: str) -> Response:
    payload = load_report(report_id)
    report = Report.model_validate(payload) if payload else None
    if not report or "/" in name or "\\" in name or name not in {h["name"] for h in report.heatmaps}:
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
        return error("not_found", "Report not found.", 404)
    rows = "".join(f"<tr><td>{html.escape(s.name)}</td><td>{s.strength}</td><td>{s.score}</td><td>{html.escape(s.reason)}</td></tr>" for s in report.signals)
    body = f"""<!doctype html><meta charset="utf-8"><title>Media Provenance Report</title>
<style>body{{font:16px sans-serif;max-width:900px;margin:2rem auto}}th,td{{padding:.5rem;border:1px solid #ccc}}</style>
<h1>Evidence report</h1><h2>{report.tier} ({report.applied_rule})</h2><p>{html.escape(report.explanation)}</p>
<table><tr><th>Module</th><th>Strength</th><th>Score</th><th>Reason</th></tr>{rows}</table>"""
    return Response(body, media_type="text/html", headers={"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'"})


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
    return cleanup_expired()


@app.get("/")
async def index() -> HTMLResponse:
    return HTMLResponse((Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8"))


app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
