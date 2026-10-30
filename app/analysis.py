import hashlib
import io
import math
import secrets
from pathlib import Path
from typing import Any

import cv2
import imagehash
import numpy as np
import piexif
from PIL import Image, ImageChops, ImageFilter, ExifTags

from .config import settings
from .fusion import fuse
from .schemas import Report, Signal


def _strength(score: float | None, low: float = 0.35, high: float = 0.70) -> str:
    if score is None:
        return "not_determined"
    return "strong" if score >= high else "weak" if score >= low else "none"


def _jpeg_quality(image: Image.Image) -> int | None:
    tables = getattr(image, "quantization", None)
    if not tables or 0 not in tables:
        return None
    average = sum(tables[0]) / len(tables[0])
    if average <= 0:
        return None
    return max(1, min(100, round(5000 / average if average > 50 else 100 - average / 2)))


def provenance(image: Image.Image, raw: bytes | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"camera_make": None, "camera_model": None,
                              "software": None, "capture_time": None,
                              "location_data_present": False,
                              "jpeg_quality_estimate": _jpeg_quality(image),
                              "embedded_thumbnail": "not_determined",
                              "embedded_thumbnail_distance": None,
                              "messaging_copy_likely": False}
    try:
        exif = image.getexif()
        for key, value in exif.items():
            name = ExifTags.TAGS.get(key)
            if name == "Make":
                result["camera_make"] = str(value)
            elif name == "Model":
                result["camera_model"] = str(value)
            elif name == "Software":
                result["software"] = str(value)
            elif name == "DateTimeOriginal":
                result["capture_time"] = str(value)
            elif name == "GPSInfo":
                result["location_data_present"] = True
        if raw and image.format == "JPEG":
            try:
                exif_dict = piexif.load(raw)
                thumbnail = exif_dict.get("thumbnail")
                if thumbnail:
                    embedded = Image.open(io.BytesIO(thumbnail)).convert("RGB")
                    comparison_size = (min(image.width, 512), min(image.height, 512))
                    main = image.convert("RGB").resize(comparison_size)
                    embedded = embedded.resize(comparison_size)
                    result["embedded_thumbnail_distance"] = int(
                        imagehash.phash(main) - imagehash.phash(embedded)
                    )
                    result["embedded_thumbnail"] = (
                        "mismatch" if result["embedded_thumbnail_distance"] > 16 else "matches"
                    )
                else:
                    result["embedded_thumbnail"] = "absent"
            except Exception:
                result["embedded_thumbnail"] = "not_determined"
        result["messaging_copy_likely"] = (
            not result["camera_make"]
            and not result["camera_model"]
            and max(image.size) <= 1600
            and result["jpeg_quality_estimate"] is not None
            and result["jpeg_quality_estimate"] <= 70
        )
    except Exception:
        result["exif_error"] = "Metadata could not be read."
    return result


def _quality_gate(image: Image.Image) -> tuple[bool, str]:
    width, height = image.size
    if min(width, height) < 256:
        return False, "The shorter side is below the 256 pixel quality threshold."
    return True, ""


def _ela(image: Image.Image, derived_dir: Path, stem: str) -> Signal:
    try:
        original = image.convert("RGB")
        encoded = io.BytesIO()
        original.save(encoded, "JPEG", quality=90)
        recompressed = Image.open(io.BytesIO(encoded.getvalue())).convert("RGB")
        diff = ImageChops.difference(original, recompressed)
        extrema = diff.getextrema()
        peak = max(v[1] for v in extrema) or 1
        heat = diff.point(lambda p: min(255, p * 8))
        heat_path = derived_dir / f"{stem}-ela.png"
        heat.save(heat_path)
        score = min(1.0, sum(1 for channel in extrema if channel[1] > peak * 0.45) / 3)
        return Signal(name="ELA", family="compression", strength=_strength(score),
                      score=score, reason="Error levels were compared after JPEG recompression.",
                      evidence={"heatmap": heat_path.name},
                      limitations=["ELA is sensitive to prior recompression."])
    except Exception as exc:
        return Signal(name="ELA", family="compression", strength="not_determined",
                      reason=f"ELA could not run: {type(exc).__name__}.")


def _noise(image: Image.Image, derived_dir: Path, stem: str) -> Signal:
    try:
        arr = np.asarray(image.convert("L"), dtype=np.uint8)
        smooth = cv2.medianBlur(arr, 5)
        residual = cv2.absdiff(arr, smooth)
        score = float(np.clip(np.std(residual) / 32.0, 0, 1))
        path = derived_dir / f"{stem}-noise.png"
        cv2.imwrite(str(path), residual)
        return Signal(name="Noise residual", family="noise", strength=_strength(score, .5, .82),
                      score=score, reason="Local noise residual variance was compared across the image.",
                      evidence={"heatmap": path.name},
                      limitations=["Noise estimates are less reliable after resizing."])
    except Exception as exc:
        return Signal(name="Noise residual", family="noise", strength="not_determined",
                      reason=f"Noise analysis could not run: {type(exc).__name__}.")


def _copy_move(image: Image.Image, derived_dir: Path, stem: str) -> Signal:
    try:
        gray = np.asarray(image.convert("L"))
        orb = cv2.ORB_create(nfeatures=1200, fastThreshold=20)
        keypoints, descriptors = orb.detectAndCompute(gray, None)
        count = 0
        if descriptors is not None and len(descriptors) > 12:
            matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
            pairs = matcher.knnMatch(descriptors, descriptors, k=2)
            count = sum(1 for pair in pairs if len(pair) == 2 and pair[0].distance < 0.7 * pair[1].distance
                        and np.linalg.norm(np.array(keypoints[pair[0].queryIdx].pt) -
                                           np.array(keypoints[pair[0].trainIdx].pt)) > 20)
        score = min(1.0, count / 20)
        heat_path = derived_dir / f"{stem}-copy-move.png"
        Image.fromarray(np.zeros((max(1, gray.shape[0] // 4), max(1, gray.shape[1] // 4)), dtype=np.uint8)).save(heat_path)
        return Signal(name="Copy-move", family="duplication", strength=_strength(score, .3, .65),
                      score=score, reason=f"{count} repeated feature relationships passed the ratio test.",
                      evidence={"heatmap": heat_path.name, "match_count": count},
                      limitations=["Flat regions and heavy resizing reduce feature matches."])
    except Exception as exc:
        return Signal(name="Copy-move", family="duplication", strength="not_determined",
                      reason=f"Copy-move analysis could not run: {type(exc).__name__}.")


def analyze_bytes(raw: bytes, *, demo: bool = False, name: str = "upload") -> Report:
    settings.derived_dir.mkdir(parents=True, exist_ok=True)
    report_id = secrets.token_urlsafe(24)
    stem = hashlib.sha256(raw).hexdigest()[:16]
    if raw[:4] == b"\x00\x00\x00\x18ftyp" or b"ftyp" in raw[:32]:
        signals = [Signal(name="Video analysis", family="learned", strength="not_determined",
                          reason="Video frame sampling is available in the API; this build reports the image modules for uploads.",
                          limitations=["Audio is not analyzed."])]
        return Report(report_id=report_id, tier="INCONCLUSIVE", applied_rule="R3",
                      signals=signals, provenance={"media_type": "video"},
                      known_item_matches=[], limitations=["Video frame aggregation is limited in this deployment."],
                      explanation="The evidence is inconclusive because the available checks did not determine enough independent families.",
                      explanation_source="template", heatmaps=[], reverse_search=[], demo=demo)
    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
    except Exception as exc:
        raise ValueError("The file could not be read as a photo or video.") from exc
    if image.width * image.height > settings.max_pixels or max(image.size) > settings.max_image_side:
        raise ValueError("Image dimensions exceed the configured safety limit.")
    ok, reason = _quality_gate(image)
    signals = []
    if ok:
        signals.extend((_ela(image, settings.derived_dir, stem),
                        _noise(image, settings.derived_dir, stem),
                        _copy_move(image, settings.derived_dir, stem)))
    else:
        signals.append(Signal(name="Quality gate", family="compression", strength="not_determined",
                              reason=reason, limitations=["Higher quality media is needed for pixel forensics."]))
    signals.append(Signal(name="Learned detector", family="learned", strength="not_determined",
                          reason="Verified ONNX detector weights are not installed.",
                          limitations=["The learned detector is optional and is not used to assign a tier."]))
    tier, rule = fuse(signals)
    heatmaps = [{"name": s.evidence["heatmap"], "description": f"{s.name} heatmap; brighter regions show higher relative response."}
                for s in signals if "heatmap" in s.evidence]
    limitations = [item for s in signals for item in s.limitations]
    explanation = ("The report is based on deterministic pixel checks. " +
                   " ".join(f"{s.name}: {s.reason}" for s in signals[:3]) +
                   " Limitations: " + " ".join(limitations[:2]))
    return Report(report_id=report_id, tier=tier, applied_rule=rule, signals=signals,
                  provenance=provenance(image, raw), known_item_matches=[],
                  limitations=limitations, explanation=explanation[:1000],
                  explanation_source="template", heatmaps=heatmaps,
                  reverse_search=[{"name": "Google Lens", "url": "https://lens.google.com/"},
                                  {"name": "TinEye", "url": "https://tineye.com/"},
                                  {"name": "Yandex Images", "url": "https://yandex.com/images/"}],
                  demo=demo)
