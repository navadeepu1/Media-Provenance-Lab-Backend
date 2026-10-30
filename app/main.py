import asyncio
import base64
import html
import io
import secrets
import time
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image

from .analysis import analyze_bytes
from .config import settings
from .schemas import Report, Sample

app = FastAPI(title="Media Provenance Lab", docs_url=None, redoc_url=None)
reports: dict[str, Report] = {}
jobs: dict[str, dict] = {}
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
            jobs[job_id].update(current_module=module, progress=min(90, jobs[job_id]["progress"] + 18))
            await asyncio.sleep(0)
        report = await asyncio.to_thread(analyze_bytes, raw, demo=demo)
        reports[report.report_id] = report
        jobs[job_id].update(status="done", progress=100, report_id=report.report_id, finished_at=time.time())
    except ValueError as exc:
        jobs[job_id].update(status="failed", error_code="validation_error", error_message=str(exc), finished_at=time.time())
    except Exception:
        jobs[job_id].update(status="failed", error_code="internal_error", finished_at=time.time())


async def begin(raw: bytes, demo: bool = False) -> dict:
    job_id = secrets.token_urlsafe(18)
    jobs[job_id] = {"job_id": job_id, "status": "queued", "current_module": "queued",
                    "progress": 0, "report_id": None, "error_code": None}
    jobs[job_id]["status"] = "running"
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
    if job_id not in jobs:
        return error("not_found", "Job not found.", 404)
    return jobs[job_id]


@app.get("/api/v1/reports/{report_id}")
async def get_report(report_id: str) -> Report:
    report = reports.get(report_id)
    if not report:
        return error("not_found", "Report not found.", 404)
    return report


@app.get("/api/v1/reports/{report_id}/heatmaps/{name}")
async def get_heatmap(report_id: str, name: str) -> Response:
    report = reports.get(report_id)
    if not report or "/" in name or "\\" in name or name not in {h["name"] for h in report.heatmaps}:
        return error("not_found", "Heatmap not found.", 404)
    path = settings.derived_dir / name
    if not path.is_file():
        return error("expired", "This heatmap has expired.", 410)
    return Response(path.read_bytes(), media_type="image/png")


@app.get("/api/v1/reports/{report_id}/export")
async def export_report(report_id: str) -> Response:
    report = reports.get(report_id)
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


@app.get("/")
async def index() -> HTMLResponse:
    return HTMLResponse((Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8"))


app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
