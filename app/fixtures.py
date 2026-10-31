"""Deterministic synthetic scenes for demo samples and tests.

The scenes have texture on purpose. Flat colour has no sensor-like noise and no
keypoints, so every forensic module reports "none" for the wrong reason.
"""

from __future__ import annotations

import io
import tempfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

SCENE_SIZE = (640, 480)   # both sides above 256 px, so the quality gate can pass
VIDEO_SIZE = (384, 288)


def scene(seed: int = 1, size: tuple[int, int] = SCENE_SIZE) -> Image.Image:
    """Smooth gradients, sensor-like noise, and a few coloured blocks."""
    rng = np.random.default_rng(seed)
    width, height = size
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    base = np.stack([
        110 + 60 * np.sin(xx / 53.0 + seed),
        120 + 50 * np.cos(yy / 67.0),
        140 + 40 * np.sin((xx + yy) / 91.0),
    ], axis=2)
    noise = rng.normal(0.0, 8.0, size=(height, width, 1)).astype(np.float32)
    image = Image.fromarray(np.clip(base + noise, 0, 255).astype(np.uint8))
    draw = ImageDraw.Draw(image)
    for _ in range(10):
        x0 = int(rng.integers(0, width - 100))
        y0 = int(rng.integers(0, height - 100))
        x1 = x0 + int(rng.integers(40, 100))
        y1 = y0 + int(rng.integers(40, 100))
        colour = tuple(int(c) for c in rng.integers(40, 230, size=3))
        draw.rectangle([x0, y0, x1, y1], fill=colour)
    return image


def to_jpeg_bytes(image: Image.Image, quality: int) -> bytes:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, "JPEG", quality=quality)
    return buffer.getvalue()


def recompress(image: Image.Image, quality: int) -> Image.Image:
    """One JPEG pass, as a camera or messaging app would save the file."""
    return Image.open(io.BytesIO(to_jpeg_bytes(image, quality))).convert("RGB")


def spliced(base: Image.Image, donor_seed: int = 99) -> Image.Image:
    """Paste a noisier patch that has a different JPEG history."""
    rng = np.random.default_rng(donor_seed)
    donor = recompress(scene(donor_seed).crop((0, 0, 160, 160)), quality=60)
    donor_array = np.asarray(donor, dtype=np.float32) + rng.normal(0.0, 20.0, size=(160, 160, 3))
    patch = Image.fromarray(np.clip(donor_array, 0, 255).astype(np.uint8))
    out = base.copy()
    out.paste(patch, (240, 160))  # multiples of 16, the ELA block size
    return out


def copy_moved(base: Image.Image) -> Image.Image:
    """Copy a 96 px patch and paste it elsewhere: an offset of (308, 228) px."""
    out = base.copy()
    out.paste(base.crop((60, 60, 156, 156)), (368, 288))
    return out


def forwarded(image: Image.Image) -> Image.Image:
    """A messaging-style re-encode. Quality 65 stays above the 60 quality gate."""
    return recompress(image, quality=65)


def short_video_bytes(seed: int = 1) -> bytes:
    """Three seconds at 10 fps. Frames from the second half carry a copied patch."""
    base = np.asarray(scene(seed, size=VIDEO_SIZE), dtype=np.uint8)[:, :, ::-1].copy()  # RGB to BGR
    width, height = VIDEO_SIZE
    with tempfile.TemporaryDirectory(prefix="mpl-sample-") as folder:
        path = Path(folder) / "sample.mp4"
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (width, height))
        try:
            for index in range(30):
                frame = np.roll(base, shift=index, axis=1).copy()
                if index >= 15:
                    frame[60:124, 100:164] = base[120:184, 200:264]
                writer.write(frame)
        finally:
            writer.release()
        return path.read_bytes()


def sample_images() -> dict[str, bytes]:
    """Bytes for every demo sample id used by app/main.py."""
    clean = recompress(scene(1), quality=95)
    return {
        "clean": to_jpeg_bytes(clean, 95),
        "forwarded": to_jpeg_bytes(forwarded(clean), 65),
        "spliced": to_jpeg_bytes(spliced(clean), 92),
        "copy-moved": to_jpeg_bytes(copy_moved(clean), 92),
        "known-item": to_jpeg_bytes(clean, 95),
        "known-forwarded": to_jpeg_bytes(forwarded(clean), 65),
        "short-video": short_video_bytes(),
    }