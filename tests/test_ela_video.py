"""ELA must be skipped for decoded video frames."""

from PIL import Image

from app import analysis


def test_ela_is_not_used_on_video_frames():
    frame = Image.new("RGB", (320, 288), (60, 110, 160))
    signals = analysis.image_signals(frame, "unit", from_video=True)
    ela = next(s for s in signals if s.name == "ELA")
    assert ela.strength == "not_determined"
    assert "video" in ela.reason