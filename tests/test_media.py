"""Upload hardening: magic bytes, header checks before decoding, size boundaries."""

import struct
import zlib
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import media
from app.config import settings
from app.main import app


def png_header(width: int, height: int) -> bytes:
    """A PNG with a declared size and an empty image stream. Pillow reads the header
    without allocating pixels, so this tests the guard without a large allocation."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", b"") + chunk(b"IEND", b"")


def test_sniff_recognises_supported_types_by_bytes():
    assert media.sniff_media_type(b"\xff\xd8\xff\xe0" + b"\x00" * 20) == "image"
    assert media.sniff_media_type(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20) == "image"
    assert media.sniff_media_type(b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 20) == "image"
    assert media.sniff_media_type(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 20) == "video"
    assert media.sniff_media_type(b"just some text, not media") is None


def test_corrupt_jpeg_is_rejected_with_validation_error():
    raw = b"\xff\xd8\xff" + b"not really a jpeg " * 10
    with pytest.raises(media.UploadRejected) as info:
        media.check_image_header(raw)
    assert info.value.code == "validation_error"


@pytest.mark.parametrize("raw", [
    b"RIFF\x10\x00\x00\x00WEBPVP8 " + b"\x00" * 8,
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 8,
])
def test_corrupt_supported_image_variants_are_rejected(raw):
    assert media.sniff_media_type(raw) == "image"
    with pytest.raises(media.UploadRejected) as info:
        media.check_image_header(raw)
    assert info.value.code == "validation_error"


@pytest.mark.parametrize("brand", [b"mp42", b"isom", b"avc1"])
def test_corrupt_mp4_codec_variants_are_rejected(brand):
    raw = b"\x00\x00\x00\x18ftyp" + brand + b"\x00" * 256
    with TestClient(app) as client:
        response = client.post("/api/v1/analyze",
                               files={"file": ("sample.mp4", raw, "video/mp4")})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_decompression_bomb_header_is_rejected_without_decoding():
    with pytest.raises(media.UploadRejected):
        media.check_image_header(png_header(30000, 30000))


def test_longest_side_cap_is_enforced():
    with pytest.raises(media.UploadRejected, match="pixels or smaller"):
        media.check_image_header(png_header(6000, 100))


def test_megapixel_cap_is_enforced(monkeypatch):
    monkeypatch.setattr(settings, "max_pixels", 16_000_000)
    with pytest.raises(media.UploadRejected, match="megapixels"):
        media.check_image_header(png_header(4000, 4500))  # 18 MP, both sides under 5000


def test_valid_header_returns_dimensions():
    buf = BytesIO()
    Image.new("RGB", (64, 48)).save(buf, "PNG")
    assert media.check_image_header(buf.getvalue()) == (64, 48)


def test_size_boundary_is_inclusive(monkeypatch):
    monkeypatch.setattr(settings, "max_image_bytes", 1000)
    media.check_size(b"x" * 1000, "image")  # exactly at the limit passes
    with pytest.raises(media.UploadRejected) as info:
        media.check_size(b"x" * 1001, "image")
    assert info.value.status == 413


def test_oversize_upload_returns_413_envelope(monkeypatch):
    monkeypatch.setattr(settings, "max_image_bytes", 1000)
    with TestClient(app) as client:
        response = client.post("/api/v1/analyze",
                               files={"file": ("big.jpg", b"\xff\xd8\xff" + b"0" * 2000, "image/jpeg")})
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "file_too_large"