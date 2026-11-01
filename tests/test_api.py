import io
import time
from PIL import Image
from fastapi.testclient import TestClient
from app import main
from app.config import settings
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
