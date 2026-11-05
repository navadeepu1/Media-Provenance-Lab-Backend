"""Evaluate labeled real-world media from a manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import media, video
from app.analysis import analyze_bytes
from app.config import settings

ALLOWED_SOURCE_TYPES = {"personal", "open_source"}
REQUIRED_FIELDS = {
    "id",
    "path",
    "label",
    "expected_detection",
    "source_type",
    "license",
    "source",
    "split",
    "source_url",
    "attribution_requirements",
    "download_date",
    "modification_history",
    "consent_record",
}
ALLOWED_SPLITS = {"train", "validation", "test"}


class DatasetError(ValueError):
    """The evaluation manifest or a listed media file is invalid."""


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetError(f"Could not read manifest: {path}") from exc
    if not isinstance(manifest, dict) or not isinstance(manifest.get("samples"), list):
        raise DatasetError("Manifest must be an object with a samples list.")
    if not manifest.get("dataset_id"):
        raise DatasetError("Manifest must include dataset_id.")
    return manifest


def _sample_path(dataset_root: Path, relative_path: str) -> Path:
    candidate = (dataset_root / relative_path).resolve()
    root = dataset_root.resolve()
    if candidate == root or root not in candidate.parents:
        raise DatasetError(f"Sample path escapes the dataset directory: {relative_path}")
    return candidate


def _validate_sample(item: Any, index: int, dataset_root: Path) -> tuple[dict[str, Any], Path]:
    if not isinstance(item, dict):
        raise DatasetError(f"Sample {index} must be an object.")
    missing = REQUIRED_FIELDS - item.keys()
    if missing:
        raise DatasetError(f"Sample {index} is missing: {', '.join(sorted(missing))}.")
    if not isinstance(item["id"], str) or not item["id"].strip():
        raise DatasetError(f"Sample {index} has an invalid id.")
    if not isinstance(item["label"], str) or not item["label"].strip():
        raise DatasetError(f"Sample {item['id']} must have a label.")
    if not isinstance(item["expected_detection"], bool):
        raise DatasetError(
            f"Sample {item['id']} must set expected_detection to true or false."
        )
    if item["source_type"] not in ALLOWED_SOURCE_TYPES:
        raise DatasetError(
            f"Sample {item['id']} source_type must be personal or open_source."
        )
    if item["split"] not in ALLOWED_SPLITS:
        raise DatasetError(
            f"Sample {item['id']} split must be train, validation, or test."
        )
    for field in ("license", "source"):
        if not isinstance(item[field], str) or not item[field].strip():
            raise DatasetError(f"Sample {item['id']} must include {field}.")
    if item["source_type"] == "open_source":
        if not str(item["source_url"]).startswith(("http://", "https://")):
            raise DatasetError(f"Open-source sample {item['id']} needs an HTTP source_url.")
    elif item["source_url"] != "not_applicable":
        raise DatasetError(
            f"Personal sample {item['id']} must use not_applicable for source_url."
        )
    if item["source_type"] == "personal" and (
        not isinstance(item["consent_record"], str) or not item["consent_record"].strip()
    ):
        raise DatasetError(f"Personal sample {item['id']} needs a consent_record.")
    for field in ("attribution_requirements", "download_date", "modification_history"):
        if not isinstance(item[field], (str, list)) or not item[field]:
            raise DatasetError(f"Sample {item['id']} must include {field}.")
    if item["download_date"] != "not_applicable":
        try:
            from datetime import date
            date.fromisoformat(item["download_date"])
        except (TypeError, ValueError) as exc:
            raise DatasetError(
                f"Sample {item['id']} download_date must be YYYY-MM-DD or not_applicable."
            ) from exc
    if not isinstance(item["path"], str) or not item["path"].strip():
        raise DatasetError(f"Sample {item['id']} has an invalid path.")
    return item, _sample_path(dataset_root, item["path"])


def _media_metadata(raw: bytes, path: Path) -> dict[str, Any]:
    media_type = media.sniff_media_type(raw)
    if media_type is None:
        raise DatasetError(f"{path} is not a supported JPEG, PNG, WebP, or MP4.")
    media.check_size(raw, media_type)
    if media_type == "image":
        media.check_image_header(raw)
        with Image.open(path) as image:
            image.load()
            return {
                "media_type": media_type,
                "format": image.format,
                "dimensions": [image.width, image.height],
            }
    info = video.validate_bytes(raw)
    return {
        "media_type": media_type,
        "format": path.suffix.lower().lstrip("."),
        "dimensions": [info.width, info.height],
        "duration_seconds": round(info.duration, 3),
    }


def _metrics(observations: list[dict[str, Any]]) -> dict[str, Any]:
    actual = [item["expected_detection"] for item in observations]
    predicted = [item["signal_detected"] for item in observations]
    tp = sum(a and p for a, p in zip(actual, predicted))
    tn = sum(not a and not p for a, p in zip(actual, predicted))
    fp = sum(not a and p for a, p in zip(actual, predicted))
    fn = sum(a and not p for a, p in zip(actual, predicted))
    def wilson(successes: int, total: int) -> list[float] | None:
        if not total:
            return None
        z = 1.96
        p = successes / total
        denominator = 1 + z * z / total
        centre = (p + z * z / (2 * total)) / denominator
        margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denominator
        return [round(max(0.0, centre - margin), 4), round(min(1.0, centre + margin), 4)]

    accuracy = tp + tn
    precision = tp
    recall = tp
    return {
        "accuracy": round((tp + tn) / len(actual), 4) if actual else None,
        "precision": round(tp / (tp + fp), 4) if tp + fp else None,
        "recall": round(tp / (tp + fn), 4) if tp + fn else None,
        "confidence_intervals_95": {
            "accuracy": wilson(accuracy, len(actual)),
            "precision": wilson(precision, tp + fp),
            "recall": wilson(recall, tp + fn),
        },
        "confusion_matrix": {
            "true_positive": tp,
            "true_negative": tn,
            "false_positive": fp,
            "false_negative": fn,
        },
    }


def evaluate(manifest_path: Path, output_path: Path) -> dict[str, Any]:
    manifest = _read_manifest(manifest_path)
    dataset_root = manifest_path.parent
    observations: list[dict[str, Any]] = []
    failed_count = 0
    seen_ids: set[str] = set()
    group_splits: dict[str, str] = {}
    hash_splits: dict[str, str] = {}
    for index, raw_item in enumerate(manifest["samples"]):
        item, path = _validate_sample(raw_item, index, dataset_root)
        if item["id"] in seen_ids:
            raise DatasetError(f"Duplicate sample id: {item['id']}")
        seen_ids.add(item["id"])
        group_id = item.get("group_id", item.get("derived_from", item["id"]))
        previous_split = group_splits.setdefault(group_id, item["split"])
        if previous_split != item["split"]:
            raise DatasetError(
                f"Source group {group_id} appears in both {previous_split} and {item['split']} splits."
            )
        if path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            previous_hash_split = hash_splits.setdefault(digest, item["split"])
            if previous_hash_split != item["split"]:
                raise DatasetError(
                    f"Duplicate file content appears in both {previous_hash_split} and "
                    f"{item['split']} splits."
                )
        observation = {
            "id": item["id"],
            "path": item["path"],
            "label": item["label"],
            "expected_detection": item["expected_detection"],
            "source_type": item["source_type"],
            "license": item["license"],
            "source": item["source"],
            "source_url": item["source_url"],
            "attribution_requirements": item["attribution_requirements"],
            "download_date": item["download_date"],
            "modification_history": item["modification_history"],
            "split": item["split"],
            "group_id": group_id,
        }
        try:
            if not path.is_file():
                raise DatasetError(f"Sample file does not exist: {item['path']}")
            raw = path.read_bytes()
            checksum = hashlib.sha256(raw).hexdigest()
            if item.get("sha256") and item["sha256"].lower() != checksum:
                raise DatasetError(f"SHA-256 mismatch for {item['id']}.")
            metadata = _media_metadata(raw, path)
            report = analyze_bytes(raw, name=item["id"])
            signal_detected = report.tier in {"STRONG_SIGNALS", "WEAK_SIGNALS"}
            observation.update({
                "status": "ok",
                "sha256": checksum,
                **metadata,
                "tier": report.tier,
                "rule": report.applied_rule,
                "signal_detected": signal_detected,
                "signal_scores": {
                    signal.name: signal.score for signal in report.signals
                    if signal.score is not None
                },
            })
        except (OSError, ValueError, TypeError) as exc:
            failed_count += 1
            observation.update({"status": "error", "error": str(exc)})
        observations.append(observation)

    successful = [item for item in observations if item["status"] == "ok"]
    by_label: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_source: Counter[str] = Counter()
    for observation in successful:
        by_label[observation["label"]].append(observation)
        by_source[observation["source_type"]] += 1
    per_class = {}
    for label, rows in sorted(by_label.items()):
        class_metrics = _metrics(rows)
        class_metrics["count"] = len(rows)
        class_metrics["detected"] = sum(row["signal_detected"] for row in rows)
        per_class[label] = class_metrics
    result = {
        "schema_version": "1.0",
        "dataset_id": manifest["dataset_id"],
        "generated_by": "scripts/evaluate_dataset.py",
        "sample_count": len(observations),
        "successful_count": len(successful),
        "failed_count": failed_count,
        "source_group_count": len({item["group_id"] for item in observations}),
        "source_counts": dict(sorted(by_source.items())),
        "metrics": _metrics(successful),
        "per_class": per_class,
        "observations": observations,
        "limitations": [
            "Metrics are valid only for the labels and expected_detection values supplied by the manifest.",
            "This evaluator does not establish real-world accuracy or generalization.",
            "Threshold calibration must use a separate validation split from the reported test results.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "eval_data" / "manifest.json")
    parser.add_argument("--output", type=Path, default=ROOT / "eval" / "real_results.json")
    args = parser.parse_args()
    try:
        result = evaluate(args.manifest, args.output)
    except DatasetError as exc:
        parser.error(str(exc))
    print(json.dumps({
        "dataset_id": result["dataset_id"],
        "sample_count": result["sample_count"],
        "source_counts": result["source_counts"],
        "metrics": result["metrics"],
        "output": str(args.output),
    }, indent=2))


if __name__ == "__main__":
    main()
