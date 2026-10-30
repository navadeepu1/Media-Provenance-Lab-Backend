"""Tests for connecting the learned detector to the analysis pipeline."""

import io

from PIL import Image

from app import analysis
from app import detector as det


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (300, 300), (90, 140, 200)).save(buf, "PNG")
    return buf.getvalue()


def _fake_signal(strength: str, score: float | None) -> dict:
    return {
        "name": "learned_detector",
        "family": "learned",
        "strength": strength,
        "score": score,
        "reason": "test signal",
        "evidence": {},
        "limitations": ["test limitation"],
    }


def _learned(report):
    matches = [s for s in report.signals if s.name == "learned_detector"]
    assert len(matches) == 1
    return matches[0]


def test_detector_signal_is_included_in_report(monkeypatch):
    monkeypatch.setattr(analysis, "run_learned_detector",
                        lambda image: _fake_signal("strong", 0.95))
    signal = _learned(analysis.analyze_bytes(_png()))
    assert signal.strength == "strong"
    assert signal.score == 0.95


def test_detector_failure_stays_not_determined(monkeypatch):
    monkeypatch.setattr(analysis, "run_learned_detector",
                        lambda image: _fake_signal("not_determined", None))
    signal = _learned(analysis.analyze_bytes(_png()))
    assert signal.strength == "not_determined"
    assert signal.score is None


def test_detector_does_not_change_tier_while_uncalibrated(monkeypatch):
    assert analysis.LEARNED_COUNTS_IN_TIER is False
    raw = _png()
    monkeypatch.setattr(analysis, "run_learned_detector",
                        lambda image: _fake_signal("strong", 0.99))
    tier_with_strong = analysis.analyze_bytes(raw).tier
    monkeypatch.setattr(analysis, "run_learned_detector",
                        lambda image: _fake_signal("not_determined", None))
    tier_without = analysis.analyze_bytes(raw).tier
    assert tier_with_strong == tier_without


def test_unexpected_detector_error_is_contained(monkeypatch):
    def broken():
        raise RuntimeError("boom")

    monkeypatch.setattr(det, "get_detector", broken)
    signal = det.run_learned_detector(Image.new("RGB", (8, 8)))
    assert signal["strength"] == "not_determined"
    assert signal["score"] is None