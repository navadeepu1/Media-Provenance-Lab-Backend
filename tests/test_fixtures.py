"""Forensic checks against synthetic manipulations."""

import pytest

from app import analysis, fixtures


def _signals(image, stem):
    return {s.name: s for s in analysis.image_signals(image, stem)}


@pytest.fixture(scope="module")
def clean():
    return fixtures.recompress(fixtures.scene(1), quality=95)


@pytest.fixture(scope="module")
def clean_signals(clean):
    return _signals(clean, "fx-clean")


def test_clean_scene_is_not_strong_for_ela(clean_signals):
    assert clean_signals["ELA"].strength != "strong"


def test_splice_is_flagged_by_ela(clean):
    assert _signals(fixtures.spliced(clean), "fx-sp")["ELA"].strength in {"weak", "strong"}


def test_splice_raises_ela_score(clean, clean_signals):
    spliced = _signals(fixtures.spliced(clean), "fx-sp2")
    assert spliced["ELA"].score > clean_signals["ELA"].score


def test_splice_raises_noise_score(clean, clean_signals):
    spliced = _signals(fixtures.spliced(clean), "fx-sn")
    assert spliced["Noise residual"].score > clean_signals["Noise residual"].score


def test_forwarded_copy_is_not_flagged(clean):
    signals = _signals(fixtures.forwarded(clean), "fx-fw")
    pixel = [s for s in signals.values() if s.family != "learned"]
    assert all(s.strength in {"none", "not_determined"} for s in pixel)


def test_copy_move_finds_the_copied_patch(clean):
    signals = _signals(fixtures.copy_moved(clean), "fx-cm")
    assert signals["Copy-move"].evidence["match_count"] >= 10