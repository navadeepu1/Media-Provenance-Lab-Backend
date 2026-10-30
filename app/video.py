"""Video handling with OpenCV. Each upload is written to a private temporary
folder that is always removed, even when decoding fails."""

from __future__ import annotations

import math
import tempfile
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import cv2
from PIL import Image

from .config import settings

MAX_DURATION_SECONDS = 30
MAX_FRAMES = 30
MAX_FPS = 240


class VideoError(ValueError):
    """The video cannot be analysed. The message is safe to show to users."""


@dataclass(frozen=True)
class VideoInfo:
    fps: float
    frame_count: int
    width: int
    height: int

    @property
    def duration(self) -> float:
        return self.frame_count / self.fps


@dataclass(frozen=True)
class SampledFrame:
    index: int
    timestamp: float
    image: Image.Image


@contextmanager
def workspace(raw: bytes) -> Iterator[Path]:
    """Write the upload to a temporary folder and delete the folder on exit."""
    with tempfile.TemporaryDirectory(prefix="mpl-video-", ignore_cleanup_errors=True) as folder:
        path = Path(folder) / "input.mp4"
        path.write_bytes(raw)
        yield path


def _finite(value) -> float:
    number = float(value or 0.0)
    return number if math.isfinite(number) else 0.0


def probe(path: Path) -> VideoInfo:
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise VideoError("The video could not be opened. Use an H.264 MP4 file.")
        fps = _finite(capture.get(cv2.CAP_PROP_FPS))
        count = int(_finite(capture.get(cv2.CAP_PROP_FRAME_COUNT)))
        width = int(_finite(capture.get(cv2.CAP_PROP_FRAME_WIDTH)))
        height = int(_finite(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    finally:
        capture.release()

    if not (0 < fps <= MAX_FPS) or count <= 0:
        raise VideoError("The video timing could not be read. Use an H.264 MP4 file.")
    if width <= 0 or height <= 0:
        raise VideoError("The video frame size could not be read.")
    if max(width, height) > settings.max_image_side:
        raise VideoError(f"Video frames must be {settings.max_image_side} pixels or smaller on the longest side.")
    if width * height > settings.max_pixels:
        raise VideoError(f"Video frames must be {settings.max_pixels / 1_000_000:g} megapixels or smaller.")

    info = VideoInfo(fps=fps, frame_count=count, width=width, height=height)
    if info.duration > MAX_DURATION_SECONDS:
        raise VideoError("Video must be 30 seconds or shorter.")
    return info


def target_indices(info: VideoInfo) -> list[int]:
    """One frame per second, at most 30. Clips shorter than a second still get one frame."""
    seconds = min(MAX_FRAMES, max(1, math.ceil(info.duration)))
    indices: list[int] = []
    for second in range(seconds):
        index = min(round(second * info.fps), info.frame_count - 1)
        if not indices or index > indices[-1]:
            indices.append(index)
    return indices


def sample_frames(path: Path, info: VideoInfo) -> Iterator[SampledFrame]:
    """Yield the target frames in order. Skipped frames are grabbed, not converted."""
    targets = target_indices(info)
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise VideoError("The video could not be opened. Use an H.264 MP4 file.")
        position = 0
        for target in targets:
            while position < target:
                if not capture.grab():
                    return
                position += 1
            ok, frame = capture.read()
            if not ok or frame is None:
                return
            position += 1
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            yield SampledFrame(index=target, timestamp=target / info.fps, image=Image.fromarray(rgb))
    finally:
        capture.release()


def validate_bytes(raw: bytes) -> VideoInfo:
    """Check an upload before it is queued: timing, limits, and at least one decodable frame."""
    with workspace(raw) as path:
        info = probe(path)
        with closing(sample_frames(path, info)) as frames:
            if next(frames, None) is None:
                raise VideoError("No frames could be decoded. Use an H.264 MP4 file.")
        return info
    