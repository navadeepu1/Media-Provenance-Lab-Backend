"""Forensic analysis for uploaded photos and videos.

Every module returns a Signal. A module that cannot run returns "not_determined"
with a reason. It never returns a clean result.
"""

from __future__ import annotations

import hashlib
import io
import math
import secrets
from contextlib import closing
from dataclasses import dataclass
from typing import Any

import cv2
import imagehash
import numpy as np
import piexif
from PIL import ExifTags, Image, ImageChops

from . import c2pa, media, video
from . import known_items
from .config import settings
from .detector import run_learned_detector
from .explainer import explain
from .fusion import fuse
from .schemas import Report, Signal

# Keep False until the detector is calibrated on the validation split and the
# decision is recorded in docs/METHODOLOGY.md.
LEARNED_COUNTS_IN_TIER = False

STRONG = "STRONG_SIGNALS"
WEAK = "WEAK_SIGNALS"
NONE = "NO_SIGNALS"
INCONCLUSIVE = "INCONCLUSIVE"

REVERSE_SEARCH = [
    {"name": "Google Lens", "url": "https://lens.google.com/"},
    {"name": "TinEye", "url": "https://tineye.com/"},
    {"name": "Yandex Images", "url": "https://yandex.com/images/"},
]


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
    quality = _jpeg_quality(image)
    if quality is not None and quality < 60:
        return False, "The estimated JPEG quality is below the 60 quality threshold."
    return True, ""


ELA_BLOCK = 16               # block size in pixels
ELA_RECOMPRESS_QUALITY = 90
ELA_Z_OUTLIER = 4.0          # robust z-score a block must exceed
ELA_MIN_LEVEL_GAP = 1.0      # and sit this many 0-255 levels above the median
ELA_WEAK_FRACTION = 0.02     # share of flagged blocks for a weak signal
ELA_STRONG_FRACTION = 0.10   # share of flagged blocks for a strong signal
ELA_STRONG_REGION = 4        # strong also needs one connected group this many blocks
FORENSIC_TILE_SIZE = 1024


def _tiled_blocks(values: np.ndarray, block_size: int, reducer: str) -> np.ndarray:
    """Reduce aligned blocks without creating a full block-view copy."""
    height, width = values.shape
    block_rows, block_cols = height // block_size, width // block_size
    output = np.empty((block_rows, block_cols), dtype=np.float32)
    for row in range(0, block_rows, max(1, FORENSIC_TILE_SIZE // block_size)):
        for col in range(0, block_cols, max(1, FORENSIC_TILE_SIZE // block_size)):
            row_end = min(block_rows, row + FORENSIC_TILE_SIZE // block_size)
            col_end = min(block_cols, col + FORENSIC_TILE_SIZE // block_size)
            tile = values[
                row * block_size:row_end * block_size,
                col * block_size:col_end * block_size,
            ]
            view = tile.reshape(row_end - row, block_size, col_end - col, block_size)
            reduced = view.mean(axis=(1, 3)) if reducer == "mean" else view.std(axis=(1, 3))
            output[row:row_end, col:col_end] = reduced
    return output


def _largest_region(mask: np.ndarray) -> int:
    """Size, in blocks, of the largest 8-connected group of flagged blocks."""
    if not mask.any():
        return 0
    _, _, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    return int(stats[1:, cv2.CC_STAT_AREA].max())


def _ela(image: Image.Image, derived_dir, stem: str) -> Signal:
    """Block-level error level analysis.

    The image is recompressed at a fixed quality and compared with the original.
    Each 16x16 block gets a mean error. A block is flagged when its error is a
    robust outlier against the rest of the image (median and MAD) and sits above
    the median. Strength depends on the share of flagged blocks and on whether
    they form one connected group. All thresholds are provisional until tested
    on the validation split."""
    try:
        original = image.convert("RGB")
        encoded = io.BytesIO()
        original.save(encoded, "JPEG", quality=ELA_RECOMPRESS_QUALITY)
        recompressed = Image.open(io.BytesIO(encoded.getvalue())).convert("RGB")
        diff = np.abs(
            np.asarray(original, dtype=np.float32) - np.asarray(recompressed, dtype=np.float32)
        ).mean(axis=2)

        bh, bw = diff.shape[0] // ELA_BLOCK, diff.shape[1] // ELA_BLOCK
        if bh < 2 or bw < 2:
            return Signal(name="ELA", family="compression", strength="not_determined",
                          reason="The image is too small for block-level ELA.")
        cropped = diff[: bh * ELA_BLOCK, : bw * ELA_BLOCK]
        blocks = _tiled_blocks(cropped, ELA_BLOCK, "mean")

        median = float(np.median(blocks))
        mad = float(np.median(np.abs(blocks - median)))
        spread = max(1.4826 * mad, 0.25)
        excess = blocks - median
        z = excess / spread
        flagged = (z > ELA_Z_OUTLIER) & (excess >= ELA_MIN_LEVEL_GAP)

        fraction = float(flagged.mean())
        region = _largest_region(flagged)
        if fraction >= ELA_STRONG_FRACTION and region >= ELA_STRONG_REGION:
            strength = "strong"
        elif fraction >= ELA_WEAK_FRACTION:
            strength = "weak"
        else:
            strength = "none"

        heat = np.clip(z / ELA_Z_OUTLIER * 127, 0, 255).astype(np.uint8)
        heat = cv2.resize(heat, (bw * ELA_BLOCK, bh * ELA_BLOCK), interpolation=cv2.INTER_NEAREST)
        heat_path = derived_dir / f"{stem}-ela.png"
        cv2.imwrite(str(heat_path), cv2.applyColorMap(heat, cv2.COLORMAP_JET))

        flagged_count = int(flagged.sum())
        return Signal(name="ELA", family="compression", strength=strength,
                      score=round(fraction, 4),
                      reason=(f"{flagged_count} of {flagged.size} blocks ({fraction:.1%}) have error "
                              f"levels that stand out from the rest of the image; the largest "
                              f"group is {region} blocks."),
                      evidence={"heatmap": heat_path.name, "flagged_blocks": flagged_count,
                                "largest_region_blocks": region},
                      limitations=["ELA is sensitive to prior recompression.",
                                   "Block size and thresholds are provisional until validated."])
    except Exception as exc:
        return Signal(name="ELA", family="compression", strength="not_determined",
                      reason=f"ELA could not run: {type(exc).__name__}.")

NOISE_BLOCK = 16             # block size in pixels, same grid as ELA
NOISE_Z_OUTLIER = 4.0        # robust z-score a block must exceed
NOISE_MIN_LEVEL_GAP = 0.5    # and sit this many residual levels above the median
NOISE_WEAK_FRACTION = 0.02
NOISE_STRONG_FRACTION = 0.10
NOISE_STRONG_REGION = 4


def _noise(image: Image.Image, derived_dir, stem: str) -> Signal:
    """Block-level noise residual.

    A median filter removes the image content, leaving the residual. Each 16x16
    block gets the standard deviation of its residual. Blocks whose noise stands
    out from the rest of the image are flagged, using the same robust z-score
    and connected-region rules as ELA. Thresholds are provisional until
    validated on the validation split."""
    try:
        gray = np.asarray(image.convert("L"), dtype=np.uint8)
        residual = cv2.absdiff(gray, cv2.medianBlur(gray, 5)).astype(np.float32)

        bh, bw = residual.shape[0] // NOISE_BLOCK, residual.shape[1] // NOISE_BLOCK
        if bh < 2 or bw < 2:
            return Signal(name="Noise residual", family="noise", strength="not_determined",
                          reason="The image is too small for block-level noise analysis.")
        cropped = residual[: bh * NOISE_BLOCK, : bw * NOISE_BLOCK]
        blocks = _tiled_blocks(cropped, NOISE_BLOCK, "std")

        median = float(np.median(blocks))
        mad = float(np.median(np.abs(blocks - median)))
        spread = max(1.4826 * mad, 0.25)
        excess = blocks - median
        z = excess / spread
        flagged = (z > NOISE_Z_OUTLIER) & (excess >= NOISE_MIN_LEVEL_GAP)

        fraction = float(flagged.mean())
        region = _largest_region(flagged)
        if fraction >= NOISE_STRONG_FRACTION and region >= NOISE_STRONG_REGION:
            strength = "strong"
        elif fraction >= NOISE_WEAK_FRACTION:
            strength = "weak"
        else:
            strength = "none"

        heat = np.clip(z / NOISE_Z_OUTLIER * 127, 0, 255).astype(np.uint8)
        heat = cv2.resize(heat, (bw * NOISE_BLOCK, bh * NOISE_BLOCK), interpolation=cv2.INTER_NEAREST)
        heat_path = derived_dir / f"{stem}-noise.png"
        cv2.imwrite(str(heat_path), cv2.applyColorMap(heat, cv2.COLORMAP_JET))

        flagged_count = int(flagged.sum())
        return Signal(name="Noise residual", family="noise", strength=strength,
                      score=round(fraction, 4),
                      reason=(f"{flagged_count} of {flagged.size} blocks ({fraction:.1%}) have noise "
                              f"that stands out from the rest of the image; the largest group is "
                              f"{region} blocks."),
                      evidence={"heatmap": heat_path.name, "flagged_blocks": flagged_count,
                                "largest_region_blocks": region},
                      limitations=["Edges and fine texture can raise residual noise.",
                                   "Block size and thresholds are provisional until validated."])
    except Exception as exc:
        return Signal(name="Noise residual", family="noise", strength="not_determined",
                      reason=f"Noise analysis could not run: {type(exc).__name__}.")

def _copy_move(image: Image.Image) -> Signal:
    """Find repeated patches and require a spatially coherent source/destination region."""
    try:
        gray = np.asarray(image.convert("L"))
        orb = cv2.ORB_create(nfeatures=1500, fastThreshold=20)
        keypoints, descriptors = orb.detectAndCompute(gray, None)
        votes: dict[tuple[int, int], int] = {}
        matches: list[tuple[np.ndarray, np.ndarray, tuple[int, int]]] = []
        if descriptors is not None and len(keypoints) > 12:
            matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
            neighbours = matcher.knnMatch(descriptors, descriptors, k=3)
            for i, candidates in enumerate(neighbours):
                others = [m for m in candidates if m.trainIdx != i]  # skip the keypoint itself
                if len(others) < 2:
                    continue
                best, second = others[0], others[1]
                if best.distance >= 0.75 * second.distance:  # ratio test
                    continue
                p = np.array(keypoints[i].pt)
                q = np.array(keypoints[best.trainIdx].pt)
                dx, dy = q - p
                if math.hypot(dx, dy) < 20:
                    continue
                key = (int(round(dx / 4)), int(round(dy / 4)))  # 4 px bins
                votes[key] = votes.get(key, 0) + 1
                matches.append((p, q, key))

        best_count, best_offset = 0, (0, 0)
        for bx, by in votes:
            total = sum(votes.get((bx + i, by + j), 0) for i in (-1, 0, 1) for j in (-1, 0, 1))
            if total > best_count:
                best_count, best_offset = total, (bx * 4, by * 4)

        cluster = [
            (p, q) for p, q, key in matches
            if abs(key[0] - round(best_offset[0] / 4)) <= 1
            and abs(key[1] - round(best_offset[1] / 4)) <= 1
        ]
        region_valid = len(cluster) >= 6
        source_bbox = destination_bbox = None
        if region_valid:
            source = np.asarray([p for p, _ in cluster])
            destination = np.asarray([q for _, q in cluster])
            source_bbox = [round(float(source[:, 0].min())), round(float(source[:, 1].min())),
                           round(float(source[:, 0].max())), round(float(source[:, 1].max()))]
            destination_bbox = [round(float(destination[:, 0].min())), round(float(destination[:, 1].min())),
                                round(float(destination[:, 0].max())), round(float(destination[:, 1].max()))]
            region_valid = (source_bbox[2] - source_bbox[0] >= 16
                            and source_bbox[3] - source_bbox[1] >= 16)
        validated_count = len(cluster) if region_valid else 0
        score = min(1.0, validated_count / 20)
        if best_count:
            reason = (f"{best_count} keypoint pairs share one displacement of about "
                      f"{best_offset[0]}, {best_offset[1]} pixels.")
        else:
            reason = "No keypoint pairs shared a displacement."
        return Signal(name="Copy-move", family="duplication", strength=_strength(score, 0.5, 0.8),
                      score=score, reason=reason,
                      evidence={"match_count": best_count, "validated_match_count": validated_count,
                                "offset_px": list(best_offset), "region_valid": region_valid,
                                "source_bbox": source_bbox, "destination_bbox": destination_bbox},
                      limitations=["Flat regions and heavy resizing reduce feature matches.",
                                   "Region validation requires a coherent cluster of keypoints."])
    except Exception as exc:
        return Signal(name="Copy-move", family="duplication", strength="not_determined",
                      reason=f"Copy-move analysis could not run: {type(exc).__name__}.")


def image_signals(image: Image.Image, stem: str, *, from_video: bool = False) -> list[Signal]:
    derived = settings.derived_dir
    ok, reason = _quality_gate(image)
    signals: list[Signal] = []
    if ok:
        if from_video:
            signals.append(Signal(
                name="ELA", family="compression", strength="not_determined",
                reason="ELA is not used on decoded video frames: they are already lossy-compressed, "
                       "so recompression measures the codec rather than edits.",
                limitations=["ELA is not applied to video frames until it is validated on video."]))
        else:
            signals.append(_ela(image, derived, stem))
        signals.append(_noise(image, derived, stem))
        signals.append(_copy_move(image))
    else:
        signals.append(Signal(name="Quality gate", family="compression", strength="not_determined",
                              reason=reason,
                              limitations=["Higher quality media is needed for pixel forensics."]))
        for name, family in (("ELA", "compression"), ("Noise residual", "noise"),
                             ("Copy-move", "duplication")):
            signals.append(Signal(name=name, family=family, strength="not_determined",
                                  reason="Skipped: the quality gate did not pass.", limitations=[]))
    signals.append(Signal.model_validate(run_learned_detector(image)))
    return signals


def _fused(signals: list[Signal]) -> tuple[str, str]:
    counted = signals if LEARNED_COUNTS_IN_TIER else [s for s in signals if s.family != "learned"]
    return fuse(counted)


def _heatmaps(signals: list[Signal]) -> list[dict]:
    return [{"name": s.evidence["heatmap"],
             "description": f"{s.name} heatmap; brighter regions show a higher relative response."}
            for s in signals if "heatmap" in s.evidence]


def _collect_limitations(signals: list[Signal]) -> list[str]:
    return list(dict.fromkeys(item for s in signals for item in s.limitations))


def _explanation_input(tier, rule, signals, limitations, extra=None) -> dict:
    payload = {
        "tier": tier,
        "rule_id": rule,
        "signals": [{"name": s.name, "strength": s.strength, "score": s.score, "reason": s.reason}
                    for s in signals],
        "limitations": limitations,
    }
    if extra:
        payload.update(extra)
    return payload


def _report(report_id, tier, rule, signals, provenance_data, limitations,
            explanation, source, demo, known_matches=None, frame_thumbnails=None) -> Report:
    return Report(report_id=report_id, tier=tier, applied_rule=rule, signals=signals,
                  provenance=provenance_data, known_item_matches=known_matches or [], limitations=limitations,
                  explanation=explanation, explanation_source=source,
                  heatmaps=_heatmaps(signals),
                  frame_thumbnails=frame_thumbnails or [],
                  reverse_search=[dict(item) for item in REVERSE_SEARCH], demo=demo)


def _analyze_image(raw: bytes, report_id: str, stem: str, demo: bool) -> Report:
    media.check_image_header(raw)
    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
    except Exception as exc:
        raise media.UploadRejected("validation_error", "The file could not be read as a photo.", 422) from exc
    signals = image_signals(image, stem)
    tier, rule = _fused(signals)
    limitations = _collect_limitations(signals)
    explanation, source = explain(_explanation_input(tier, rule, signals, limitations))
    provenance_data = provenance(image, raw)
    provenance_data["c2pa"] = c2pa.inspect_bytes(raw, ".jpg")
    return _report(report_id, tier, rule, signals, provenance_data, limitations,
                   explanation, source, demo, known_matches=known_items.match(image))


@dataclass(frozen=True)
class _FrameResult:
    timestamp: float
    tier: str
    rule: str
    signals: list[Signal]
    image: Image.Image


def aggregate_frame_tiers(tiers: list[str]) -> tuple[str, str, int]:
    """Combine per-frame tiers into one video tier.
    Returns (tier, rule ID, strong-frame threshold)."""
    count = len(tiers)
    if count == 0:
        return INCONCLUSIVE, "R3", 0
    threshold = max(2, math.ceil(0.10 * count))
    strong = tiers.count(STRONG)
    if strong >= threshold:
        return STRONG, "R1", threshold
    if strong or tiers.count(WEAK):
        return WEAK, "R2", threshold
    if tiers.count(INCONCLUSIVE) * 2 > count:
        return INCONCLUSIVE, "R3", threshold
    return NONE, "R4", threshold


def _rank(signal: Signal) -> tuple[bool, float]:
    return (signal.score is not None, signal.score or 0.0)


def _strongest_per_module(frames: list[_FrameResult]) -> list[Signal]:
    best: dict[str, tuple[_FrameResult, Signal]] = {}
    for frame in frames:
        for signal in frame.signals:
            current = best.get(signal.name)
            if current is None or _rank(signal) > _rank(current[1]):
                best[signal.name] = (frame, signal)
    return [
        signal.model_copy(update={
            "reason": f"Strongest sampled frame at {frame.timestamp:.0f} s. {signal.reason or ''}".strip()
        })
        for frame, signal in best.values()
    ]


def _frame_thumbnails(frames: list[_FrameResult], stem: str) -> list[dict[str, str]]:
    ranked = sorted(
        frames,
        key=lambda frame: (
            {STRONG: 3, WEAK: 2, NONE: 1, INCONCLUSIVE: 0}[frame.tier],
            max((signal.score or 0 for signal in frame.signals), default=0),
        ),
        reverse=True,
    )
    thumbnails = []
    for frame in ranked[:3]:
        name = f"{stem}-frame-{int(frame.timestamp):04d}.jpg"
        path = settings.derived_dir / name
        thumbnail = frame.image.convert("RGB")
        thumbnail.thumbnail((640, 640))
        thumbnail.save(path, "JPEG", quality=85)
        thumbnails.append({
            "name": name,
            "timestamp_seconds": str(round(frame.timestamp, 2)),
            "tier": frame.tier,
            "description": f"Strongest sampled frame at {frame.timestamp:.2f} seconds ({frame.tier}).",
        })
    return thumbnails


def _analyze_video(raw: bytes, report_id: str, stem: str, demo: bool) -> Report:
    frames: list[_FrameResult] = []
    heatmap_names: set[str] = set()
    info: video.VideoInfo | None = None
    try:
        with video.workspace(raw) as path:
            info = video.probe(path)
            with closing(video.sample_frames(path, info)) as sampled_frames:
                for sampled in sampled_frames:
                    signals = image_signals(sampled.image, f"{stem}-f{sampled.index}", from_video=True)
                    tier, rule = _fused(signals)
                    frames.append(_FrameResult(sampled.timestamp, tier, rule, signals, sampled.image.copy()))
                    heatmap_names.update(h["name"] for h in _heatmaps(signals))
    except video.VideoError as exc:
        raise media.UploadRejected("validation_error", str(exc), 422) from exc

    if info is None or not frames:
        raise media.UploadRejected("validation_error",
                                   "No frames could be decoded. Use an H.264 MP4 file.", 422)

    tier, rule, threshold = aggregate_frame_tiers([f.tier for f in frames])
    chosen = _strongest_per_module(frames)
    frame_thumbnails = _frame_thumbnails(frames, stem)

    # Keep heatmaps only for the strongest frames. Delete the rest to save disk space.
    keep = {h["name"] for h in _heatmaps(chosen)} | {item["name"] for item in frame_thumbnails}
    for name in heatmap_names - keep:
        (settings.derived_dir / name).unlink(missing_ok=True)

    limitations = [
        "Only up to 30 frames are sampled, one per second. Edits between sampled frames are not seen.",
        "Audio is not analyzed.",
    ]
    limitations = list(dict.fromkeys(limitations + _collect_limitations(chosen)))
    strong_frames = sum(f.tier == STRONG for f in frames)

    provenance_data = {
        "media_type": "video",
        "c2pa": c2pa.inspect_bytes(raw, ".mp4"),
        "duration_seconds": round(info.duration, 2),
        "frames_per_second": round(info.fps, 2),
        "frames_analysed": len(frames),
        "sample_interval_seconds": 1,
        "strong_frame_threshold": threshold,
        "strong_frames": strong_frames,
         "frame_tiers": [
            {"timestamp_seconds": round(f.timestamp, 2), "tier": f.tier,
             "strengths": {s.name: s.strength for s in f.signals}}
            for f in frames
        ],
    }
    explanation, source = explain(_explanation_input(
        tier, rule, chosen, limitations,
        extra={"frames": {"analysed": len(frames), "strong": strong_frames, "threshold": threshold}},
    ))
    return _report(report_id, tier, rule, chosen, provenance_data, limitations,
                   explanation, source, demo, frame_thumbnails=frame_thumbnails)


def analyze_bytes(raw: bytes, *, demo: bool = False, name: str = "upload") -> Report:
    settings.derived_dir.mkdir(parents=True, exist_ok=True)
    media_type = media.sniff_media_type(raw)
    if media_type is None:
        raise media.UploadRejected("invalid_file_type", "Upload a JPEG, PNG, WebP, or MP4 file.", 415)
    media.check_size(raw, media_type)
    report_id = secrets.token_urlsafe(24)
    stem = hashlib.sha256(raw).hexdigest()[:16]
    if media_type == "video":
        return _analyze_video(raw, report_id, stem, demo)
    return _analyze_image(raw, report_id, stem, demo)