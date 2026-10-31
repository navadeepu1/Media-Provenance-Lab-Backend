"""Block-level ELA: smooth images stay quiet, a pasted noisy patch is flagged,
and the connected-region counter works."""

import io

import numpy as np
import pytest
from PIL import Image

from app import analysis


def _gradient(size=(320, 320)) -> Image.Image:
    x = np.linspace(0, 255, size[0], dtype=np.float32)
    y = np.linspace(0, 255, size[1], dtype=np.float32)
    xx, yy = np.meshgrid(x, y)
    rgb = np.dstack([xx, yy, (xx + yy) / 2]).astype(np.uint8)
    return Image.fromarray(rgb)


def _jpeg_roundtrip(img: Image.Image, quality: int) -> Image.Image:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality)
    return Image.open(io.BytesIO(buf.getvalue())).convert("RGB")


@pytest.fixture
def out(tmp_path):
    return tmp_path


def test_smooth_image_is_not_flagged(out):
    clean = _jpeg_roundtrip(_gradient(), quality=95)
    assert analysis._ela(clean, out, "clean").strength == "none"


def test_pasted_noisy_patch_is_flagged_strong(out):
    base = _jpeg_roundtrip(_gradient(), quality=95)
    rng = np.random.default_rng(7)
    noise = Image.fromarray(rng.integers(0, 256, size=(128, 128, 3), dtype=np.uint8))
    spliced = base.copy()
    spliced.paste(noise, (96, 96))  # 96 and 224 are multiples of the 16 px block size
    signal = analysis._ela(spliced, out, "spliced")
    assert signal.strength == "strong"
    assert (out / signal.evidence["heatmap"]).exists()


def test_largest_region_counts_connected_blocks():
    mask = np.zeros((6, 6), dtype=bool)
    mask[1:3, 1:3] = True   # one group of 4 blocks
    mask[5, 5] = True       # an isolated block
    assert analysis._largest_region(mask) == 4
    assert analysis._largest_region(np.zeros((3, 3), dtype=bool)) == 0