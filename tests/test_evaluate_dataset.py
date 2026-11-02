import json
from pathlib import Path

import pytest
from PIL import Image

from scripts.evaluate_dataset import DatasetError, evaluate


def _image(path: Path) -> None:
    Image.new("RGB", (640, 480), "navy").save(path, "JPEG")


def _manifest(path: Path, *, expected_detection=False) -> Path:
    image_path = path / "photo.jpg"
    _image(image_path)
    manifest_path = path / "manifest.json"
    manifest_path.write_text(json.dumps({
        "dataset_id": "test-real-data",
        "samples": [{
            "id": "photo-1",
            "path": "photo.jpg",
            "label": "authentic",
            "expected_detection": expected_detection,
            "source_type": "personal",
            "license": "private-consented",
            "source": "test fixture",
            "source_url": "not_applicable",
            "attribution_requirements": "not_applicable",
            "download_date": "not_applicable",
            "modification_history": ["test fixture"],
            "consent_record": "test consent",
            "split": "test",
        }],
    }), encoding="utf-8")
    return manifest_path


def test_evaluate_records_metadata_and_metrics(tmp_path):
    manifest = _manifest(tmp_path)
    output = tmp_path / "results.json"

    result = evaluate(manifest, output)

    assert result["sample_count"] == 1
    assert result["source_counts"] == {"personal": 1}
    assert result["observations"][0]["format"] == "JPEG"
    assert result["observations"][0]["dimensions"] == [640, 480]
    assert result["metrics"]["confusion_matrix"]["true_negative"] == 1
    assert json.loads(output.read_text(encoding="utf-8"))["dataset_id"] == "test-real-data"


def test_missing_label_is_rejected(tmp_path):
    manifest = _manifest(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    del payload["samples"][0]["label"]
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(DatasetError, match="missing: label"):
        evaluate(manifest, tmp_path / "results.json")


def test_path_escape_is_rejected(tmp_path):
    manifest = _manifest(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["samples"][0]["path"] = "../outside.jpg"
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(DatasetError, match="escapes"):
        evaluate(manifest, tmp_path / "results.json")


def test_invalid_media_is_recorded_without_stopping_other_samples(tmp_path):
    manifest = _manifest(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["samples"].append({
        "id": "missing",
        "path": "missing.jpg",
        "label": "authentic",
        "expected_detection": False,
        "source_type": "personal",
        "license": "private-consented",
        "source": "test fixture",
        "source_url": "not_applicable",
        "attribution_requirements": "not_applicable",
        "download_date": "not_applicable",
        "modification_history": ["test fixture"],
        "consent_record": "test consent",
        "split": "test",
    })
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    result = evaluate(manifest, tmp_path / "results.json")

    assert result["successful_count"] == 1
    assert result["failed_count"] == 1
    assert result["observations"][1]["status"] == "error"
