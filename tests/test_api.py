import io
import time
from datetime import datetime, timedelta, timezone
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from app import main
from app.config import settings
from app.db import JobRow, ReportRow, SessionLocal, cleanup_expired
from app.main import app


def jpeg():
    out = io.BytesIO()
    Image.new("RGB", (640, 480), "navy").save(out, "JPEG")
    return out.getvalue()


def test_health_and_samples():
    with TestClient(app) as client:
        assert client.get("/api/v1/health").status_code == 200
        assert len(client.get("/api/v1/samples").json()) >= 7


def test_upload_runs_real_pipeline():
    with TestClient(app) as client:
        response = client.post("/api/v1/analyze", files={"file": ("sample.jpg", jpeg(), "image/jpeg")})
        assert response.status_code == 202
        job_id = response.json()["job_id"]
        for _ in range(300):
            job = client.get(f"/api/v1/jobs/{job_id}").json()
            if job["status"] in ("done", "failed"):
                break
            time.sleep(0.1)
        assert job["status"] == "done"
        report = client.get(f"/api/v1/reports/{job['report_id']}")
        assert report.status_code == 200
        assert report.json()["applied_rule"] in {"R1", "R2", "R3", "R4"}


def test_invalid_magic_is_rejected():
    with TestClient(app) as client:
        response = client.post("/api/v1/analyze", files={"file": ("sample.jpg", b"not an image", "image/jpeg")})
        assert response.status_code == 415


def test_security_headers_and_admin_configuration():
    with TestClient(app) as client:
        response = client.get("/")
        assert response.headers["x-content-type-options"] == "nosniff"
        assert "default-src 'none'" in response.headers["content-security-policy"]
        assert len(response.headers["x-request-id"]) == 32
        assert client.post("/api/v1/admin/cleanup").status_code == 503


def test_methodology_matches_fusion_thresholds():
    with TestClient(app) as client:
        payload = client.get("/api/v1/methodology").json()
    assert payload["thresholds"] == {"strong": 0.70, "weak": 0.35}


def test_analysis_rate_limit_returns_retryable_error(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_max_requests", 1)
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 60)
    main._rate_limit_hits.clear()
    with TestClient(app) as client:
        first = client.post("/api/v1/analyze", files={"file": ("sample.jpg", jpeg(), "image/jpeg")})
        second = client.post("/api/v1/analyze", files={"file": ("sample.jpg", jpeg(), "image/jpeg")})
    assert first.status_code == 202
    assert second.status_code == 429
    assert second.headers["retry-after"] == "60"
    assert second.json()["error"]["code"] == "rate_limited"


def test_admin_cleanup_authorization_matrix(monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", "test-admin-key")
    monkeypatch.setattr(main, "cleanup_expired", lambda: {"reports": 2, "uploads": 1})
    with TestClient(app) as client:
        assert client.post("/api/v1/admin/cleanup").status_code == 401
        assert client.post(
            "/api/v1/admin/cleanup", headers={"X-Admin-Key": "wrong"}
        ).status_code == 401
        response = client.post(
            "/api/v1/admin/cleanup", headers={"X-Admin-Key": "test-admin-key"}
        )
    assert response.status_code == 200
    assert response.json() == {"reports": 2, "uploads": 1}


@pytest.mark.parametrize("suffix", ["", "/export", "/heatmaps/example.png"])
def test_expired_report_returns_gone(suffix):
    report_id = "expired-test-report"
    with SessionLocal.begin() as session:
        session.merge(ReportRow(
            id=report_id,
            job_id="expired-test-job",
            payload="{}",
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1),
        ))
    with TestClient(app) as client:
        response = client.get(f"/api/v1/reports/{report_id}{suffix}")
    assert response.status_code == 410
    assert response.json()["error"]["code"] == "expired"


def test_cleanup_removes_expired_report_and_upload(tmp_path):
    report_id = "cleanup-test-report"
    job_id = "cleanup-test-job"
    upload = tmp_path / "upload.bin"
    upload.write_bytes(b"temporary")
    old = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=2)
    with SessionLocal.begin() as session:
        session.merge(ReportRow(
            id=report_id, job_id=job_id, payload="{}",
            created_at=old, expires_at=old,
        ))
        session.merge(JobRow(
            id=job_id, raw_path=str(upload), created_at=old,
        ))
    result = cleanup_expired()
    assert result["reports"] >= 1
    assert result["uploads"] >= 1
    assert not upload.exists()


def test_scheduled_cleanup_runs_and_stops(monkeypatch):
    calls = []
    monkeypatch.setattr(settings, "cleanup_interval_seconds", 0.01)
    monkeypatch.setattr(main, "cleanup_expired", lambda: calls.append(True) or {"reports": 0, "uploads": 0})
    with TestClient(app):
        time.sleep(0.05)
    assert calls
    assert main._cleanup_task is None or main._cleanup_task.done()
