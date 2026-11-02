import io

from PIL import Image

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
