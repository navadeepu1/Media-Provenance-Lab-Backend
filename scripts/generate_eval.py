"""Generate the reproducible synthetic evaluation manifest and results."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import fixtures
from app.analysis import analyze_bytes
from app.config import settings

OUTPUT = ROOT / "eval"
SAMPLES = OUTPUT / "generated"
LICENSE = "CC0-1.0"


def cases() -> list[dict[str, object]]:
    clean1 = fixtures.recompress(fixtures.scene(1), quality=95)
    clean2 = fixtures.recompress(fixtures.scene(2), quality=95)
    return [
        ("clean-seed-1", fixtures.to_jpeg_bytes(clean1, 95), "reference", False, "scene(1)"),
        ("clean-seed-2", fixtures.to_jpeg_bytes(clean2, 95), "reference", False, "scene(2)"),
        ("forwarded-seed-1", fixtures.to_jpeg_bytes(fixtures.forwarded(clean1), 65),
         "edited", True, "forwarded(scene(1))"),
        ("forwarded-seed-2", fixtures.to_jpeg_bytes(fixtures.forwarded(clean2), 65),
         "edited", True, "forwarded(scene(2))"),
        ("spliced-seed-1", fixtures.to_jpeg_bytes(fixtures.spliced(clean1), 92),
         "edited", True, "spliced(scene(1), donor_seed=99)"),
        ("spliced-seed-2", fixtures.to_jpeg_bytes(fixtures.spliced(clean2, donor_seed=100), 92),
         "edited", True, "spliced(scene(2), donor_seed=100)"),
        ("copy-moved-seed-1", fixtures.to_jpeg_bytes(fixtures.copy_moved(clean1), 92),
         "edited", True, "copy_moved(scene(1))"),
        ("short-video-seed-1", fixtures.short_video_bytes(1), "edited", True,
         "short_video_bytes(seed=1)"),
    ]


def write_sample(sample_id: str, raw: bytes) -> tuple[str, str]:
    suffix = ".mp4" if sample_id.startswith("short-video") else ".jpg"
    path = SAMPLES / f"{sample_id}{suffix}"
    path.write_bytes(raw)
    return str(path.relative_to(ROOT)).replace("\\", "/"), hashlib.sha256(raw).hexdigest()


def main() -> None:
    # Keep the release baseline deterministic and offline even when a local
    # optional ONNX artifact happens to exist in the developer workspace.
    settings.detector_local_path = ""
    SAMPLES.mkdir(parents=True, exist_ok=True)
    manifest_samples = []
    for index, (sample_id, raw, label, edited, generator) in enumerate(cases()):
        path, checksum = write_sample(sample_id, raw)
        manifest_samples.append({
            "id": sample_id,
            "path": path,
            "sha256": checksum,
            "media_type": "video" if path.endswith(".mp4") else "image",
            "split": ("train", "validation", "test")[index % 3],
            "label": label,
            "edited": edited,
            "generator": generator,
            "license": LICENSE,
            "attribution": "Media Provenance Lab project-generated synthetic content",
        })

    manifest = {
        "schema_version": "1.0",
        "dataset_id": "mpl-synthetic-eval-v1",
        "purpose": "Regression evaluation of deterministic evidence signals.",
        "license": LICENSE,
        "license_scope": "All generated samples in this manifest are original synthetic outputs of this repository.",
        "notices": [
            "This is not a real-world accuracy benchmark.",
            "The edited/reference labels describe the generator intent, not human forensic ground truth.",
            "Do not use these results to claim detector or production accuracy.",
        ],
        "seed_policy": "All sample seeds and transformations are recorded per item.",
        "samples": manifest_samples,
    }
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    observed = []
    for item in manifest_samples:
        report = analyze_bytes((ROOT / item["path"]).read_bytes(), name=item["id"])
        detected = report.tier in {"STRONG_SIGNALS", "WEAK_SIGNALS"}
        observed.append({
            "id": item["id"],
            "split": item["split"],
            "label": item["label"],
            "tier": report.tier,
            "rule": report.applied_rule,
            "signal_detected": detected,
        })

    positives = [item for item in observed if item["label"] == "edited"]
    references = [item for item in observed if item["label"] == "reference"]
    true_positive = sum(item["signal_detected"] for item in positives)
    false_positive = sum(item["signal_detected"] for item in references)
    false_negative = len(positives) - true_positive
    results = {
        "schema_version": "1.0",
        "manifest": manifest["dataset_id"],
        "generated_by": "scripts/generate_eval.py",
        "sample_count": len(observed),
        "split_counts": {
            split: sum(item["split"] == split for item in observed)
            for split in ("train", "validation", "test")
        },
        "metrics": {
            "metric": "signal_detected means STRONG_SIGNALS or WEAK_SIGNALS",
            "synthetic_signal_accuracy": round(
                (true_positive + len(references) - false_positive) / len(observed), 4
            ),
            "synthetic_signal_precision": round(
                true_positive / max(1, true_positive + false_positive), 4
            ),
            "synthetic_signal_recall": round(true_positive / max(1, len(positives)), 4),
            "true_positive": true_positive,
            "false_positive": false_positive,
            "false_negative": false_negative,
        },
        "limitations": manifest["notices"],
        "observations": observed,
    }
    (OUTPUT / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
