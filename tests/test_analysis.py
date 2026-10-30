import io

from PIL import Image

from app.analysis import analyze_bytes


def test_low_quality_image_reports_quality_gate():
    output = io.BytesIO()
    Image.new("RGB", (640, 480), "white").save(output, "JPEG", quality=30)
    report = analyze_bytes(output.getvalue())
    quality = next(signal for signal in report.signals if signal.name == "Quality gate")
    assert quality.strength == "not_determined"
    assert "quality" in quality.reason.lower()
