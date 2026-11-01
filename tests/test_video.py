"""Video sampling, aggregation, heatmap pruning, and temporary-file cleanup."""

import hashlib
import tempfile
from pathlib import Path

import cv2
import numpy as np
import pytest

from app import analysis, media, video
from app.config import settings
from app.video import VideoInfo

SIZE = (320, 288)  # width, height. Shorter side is at least 256, so pixel forensics run.


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Point derived files at a temporary folder. derived_dir is a read-only
    property, so patch it on the class rather than on the instance."""
    derived = tmp_path / "derived"
    monkeypatch.setattr(type(settings), "derived_dir", property(lambda self: derived))
    return tmp_path


def make_video(path: Path, seconds: float, fps: float) -> bytes:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, SIZE)
    assert writer.isOpened(), "OpenCV could not write the test video"
    for i in range(int(round(seconds * fps))):
        frame = np.full((SIZE[1], SIZE[0], 3), (40, 120, 200), dtype=np.uint8)
        x = (i * 9) % (SIZE[0] - 40)
        cv2.rectangle(frame, (x, 100), (x + 40, 140), (255, 255, 255), -1)
        writer.write(frame)
    writer.release()
    return path.read_bytes()


def _workspaces() -> set[Path]:
    return set(Path(tempfile.gettempdir()).glob("mpl-video-*"))


# --- sampling -----------------------------------------------------------------

def test_one_frame_per_second_capped_at_30():
    info = VideoInfo(fps=10, frame_count=300, width=320, height=288)  # 30 s
    assert video.target_indices(info) == [i * 10 for i in range(30)]


def test_partial_second_is_sampled():
    info = VideoInfo(fps=10, frame_count=24, width=320, height=288)  # 2.4 s
    assert video.target_indices(info) == [0, 10, 20]


def test_short_clip_still_gets_one_frame():
    info = VideoInfo(fps=10, frame_count=5, width=320, height=288)  # 0.5 s
    assert video.target_indices(info) == [0]


def test_three_second_clip_yields_three_frames(isolated):
    raw = make_video(isolated / "clip.mp4", seconds=3, fps=10)
    with video.workspace(raw) as path:
        info = video.probe(path)
        frames = list(video.sample_frames(path, info))
    assert [f.timestamp for f in frames] == [0.0, 1.0, 2.0]


def test_clip_over_30_seconds_is_rejected(isolated):
    raw = make_video(isolated / "long.mp4", seconds=31, fps=2)
    with video.workspace(raw) as path:
        with pytest.raises(video.VideoError, match="30 seconds"):
            video.probe(path)


# --- aggregation ----------------------------------------------------------------

@pytest.mark.parametrize("tiers, expected", [
    (["NO_SIGNALS"] * 10, ("NO_SIGNALS", "R4")),
    (["STRONG_SIGNALS"] * 2 + ["NO_SIGNALS"] * 8, ("STRONG_SIGNALS", "R1")),   # 10 frames, threshold 2
    (["STRONG_SIGNALS"] + ["NO_SIGNALS"] * 9, ("WEAK_SIGNALS", "R2")),
    (["STRONG_SIGNALS"] * 2 + ["NO_SIGNALS"] * 23, ("WEAK_SIGNALS", "R2")),    # 25 frames, threshold 3
    (["STRONG_SIGNALS"] * 2 + ["NO_SIGNALS"] * 28, ("WEAK_SIGNALS", "R2")),    # 30 frames, threshold 3
    (["STRONG_SIGNALS"] * 3 + ["NO_SIGNALS"] * 27, ("STRONG_SIGNALS", "R1")),
    (["WEAK_SIGNALS"] + ["NO_SIGNALS"] * 9, ("WEAK_SIGNALS", "R2")),
    (["INCONCLUSIVE"] * 6 + ["NO_SIGNALS"] * 4, ("INCONCLUSIVE", "R3")),
    (["INCONCLUSIVE"] * 4 + ["NO_SIGNALS"] * 6, ("NO_SIGNALS", "R4")),
    ([], ("INCONCLUSIVE", "R3")),
])
def test_frame_aggregation_boundaries(tiers, expected):
    tier, rule, _threshold = analysis.aggregate_frame_tiers(tiers)
    assert (tier, rule) == expected


# --- full analysis ----------------------------------------------------------------

def test_video_report_records_frame_sampling(isolated):
    raw = make_video(isolated / "clip.mp4", seconds=3, fps=10)
    report = analysis.analyze_bytes(raw)
    assert report.provenance["media_type"] == "video"
    assert report.provenance["frames_analysed"] == 3
    assert [f["timestamp_seconds"] for f in report.provenance["frame_tiers"]] == [0.0, 1.0, 2.0]


def test_only_referenced_heatmaps_remain_on_disk(isolated):
    raw = make_video(isolated / "clip.mp4", seconds=3, fps=10)
    report = analysis.analyze_bytes(raw)
    stem = hashlib.sha256(raw).hexdigest()[:16]
    on_disk = {p.name for p in settings.derived_dir.glob(f"{stem}-*")}
    referenced = {h["name"] for h in report.heatmaps}
    referenced.update(frame["name"] for frame in report.frame_thumbnails)
    assert on_disk == referenced


def test_temporary_workspace_removed_after_success(isolated):
    raw = make_video(isolated / "clip.mp4", seconds=2, fps=10)
    before = _workspaces()
    analysis.analyze_bytes(raw)
    assert _workspaces() == before


def test_temporary_workspace_removed_after_rejection(isolated):
    before = _workspaces()
    with pytest.raises(ValueError):
        analysis.analyze_bytes(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 256)
    assert _workspaces() == before


def test_fake_mp4_header_is_rejected_as_undecodable(isolated):
    raw = b"\x00\x00\x00\x20ftypisom" + b"\x00" * 256
    assert media.sniff_media_type(raw) == "video"
    with pytest.raises(media.UploadRejected) as info:
        analysis.analyze_bytes(raw)
    assert info.value.code == "validation_error"

def test_large_frames_are_downscaled_for_analysis(isolated):
    path = isolated / "big.mp4"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 2, (2048, 1152))
    for _ in range(2):
        writer.write(np.full((1152, 2048, 3), 90, dtype=np.uint8))
    writer.release()
    with video.workspace(path.read_bytes()) as work:
        info = video.probe(work)
        frames = list(video.sample_frames(work, info))
    assert frames
    assert max(frames[0].image.size) <= video.MAX_ANALYSIS_SIDE
