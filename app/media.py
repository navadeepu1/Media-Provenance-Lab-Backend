"""Upload checks: file type from magic bytes, size limits, and image headers
read before any pixel is decoded."""

from __future__ import annotations

import io

from PIL import Image

from .config import settings

MP4_BRANDS = (b"isom", b"iso2", b"iso4", b"iso5", b"iso6", b"mp41", b"mp42", b"avc1", b"M4V ")


class UploadRejected(ValueError):
    """A user-facing rejection. Subclasses ValueError so background jobs report it as a validation error."""

    def __init__(self, code: str, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def sniff_media_type(raw: bytes) -> str | None:
    """Identify the file from its first bytes. The file name is never used."""
    if raw[:3] == b"\xff\xd8\xff":
        return "image"
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "image"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image"
    if raw[4:8] == b"ftyp" and any(brand in raw[8:64] for brand in MP4_BRANDS):
        return "video"
    return None


def check_size(raw: bytes, media_type: str) -> None:
    if media_type == "video":
        limit, label = settings.max_video_bytes, "Video"
    else:
        limit, label = settings.max_image_bytes, "Image"
    if len(raw) > limit:
        raise UploadRejected("file_too_large", f"{label} must be {limit / 1_000_000:g} MB or smaller.", 413)


def check_image_header(raw: bytes) -> tuple[int, int]:
    """Read only the header. Dimensions are checked before any pixel is decoded."""
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            width, height = probe.size
    except Image.DecompressionBombError as exc:
        raise UploadRejected("validation_error", "This image is too large to process safely.") from exc
    except Exception as exc:
        raise UploadRejected("validation_error", "The file could not be read as a photo.") from exc

    if width < 1 or height < 1:
        raise UploadRejected("validation_error", "The image has no visible area.")
    if max(width, height) > settings.max_image_side:
        raise UploadRejected(
            "validation_error",
            f"Image must be {settings.max_image_side} pixels or smaller on its longest side.",
        )
    if width * height > settings.max_pixels:
        raise UploadRejected(
            "validation_error",
            f"Image must be {settings.max_pixels / 1_000_000:g} megapixels or smaller.",
        )
    return width, height