import io

import pytest
from PIL import Image

from app import fixtures
from app.analysis import analyze_bytes
from app.config import settings


def test_low_quality_image_reports_quality_gate():
    output = io.BytesIO()
    Image.new("RGB", (640, 480), "white").save(output, "JPEG", quality=30)
    report = analyze_bytes(output.getvalue())
    quality = next(signal for signal in report.signals if signal.name == "Quality gate")
    assert quality.strength == "not_determined"
    assert "quality" in quality.reason.lower()


def test_large_accepted_image_is_downscaled_for_analysis(monkeypatch):
    output = io.BytesIO()
    Image.new("RGB", (3000, 2000), "navy").save(output, "JPEG", quality=95)
    monkeypatch.setattr(settings, "analysis_max_side", 1024)

    report = analyze_bytes(output.getvalue())

    assert report.provenance["original_dimensions"] == [3000, 2000]
    assert report.provenance["analysis_dimensions"] == [1024, 683]
    assert report.provenance["analysis_resized"] is True
    assert any("downscaled" in item for item in report.limitations)


@pytest.mark.parametrize("transform", [
    fixtures.cropped,
    fixtures.resized,
    fixtures.screenshot,
    fixtures.messaging_copy,
])
def test_real_world_transform_examples_remain_analyzable(transform):
    raw = fixtures.to_jpeg_bytes(transform(fixtures.scene(7)), 90)
    report = analyze_bytes(raw)
    assert report.uncertainty["level"] in {"high", "moderate"}
    assert report.analysis_metrics["total_ms"] >= 0
