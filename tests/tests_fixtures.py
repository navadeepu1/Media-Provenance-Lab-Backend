"""The forensic modules must respond to real manipulations in textured scenes.

A failure here means a module cannot see the edit the demo claims to show.
Assertions compare against the clean scene, not against fixed numbers.
"""

import pytest

from app import analysis, fixtures


def _signals(image, stem):
    return {s.name: s for s in analysis.image_signals(image, stem)}


@pytest.fixture(scope="module")
def clean():
    return fixtures.recompress(fixtures.scene(1), quality=95)


@pytest.fixture(scope="module")
def clean_signals(clean):
    return _signals(clean, "fixture-clean")


def test_clean_scene_is_not_strong_for_ela(clean_signals):
    assert clean_signals["ELA"].strength != "strong"


def test_clean_scene_has_no_copy_move_cluster(clean_signals):
    assert clean_signals["Copy-move"].evidence.get("match_count", 0) < 10


def test_splice_raises_ela_score_above_clean(clean, clean_signals):
    signals = _signals(fixtures.spliced(clean), "fixture-spliced")
    assert signals["ELA"].score > clean_signals["ELA"].score


def test_splice_is_flagged_by_ela(clean):
    signals = _signals(fixtures.spliced(clean), "fixture-spliced-2")
    assert signals["ELA"].strength in {"weak", "strong"}


def test_copy_move_finds_the_copied_patch(clean):
    signals = _signals(fixtures.copy_moved(clean), "fixture-copy")
    assert signals["Copy-move"].evidence["match_count"] >= 10


def test_copy_move_offset_matches_the_paste(clean):
    signals = _signals(fixtures.copy_moved(clean), "fixture-copy-2")
    dx, dy = signals["Copy-move"].evidence["offset_px"]
    assert abs(abs(dx) - 308) <= 8
    assert abs(abs(dy) - 228) <= 8


def test_noise_reports_local_outliers(clean):
    # Expected to FAIL until the noise module is changed to block-level outliers.
    signals = _signals(fixtures.spliced(clean), "fixture-noise")
    assert "flagged_blocks" in signals["Noise residual"].evidence