import json

import pytest

from scripts.calibrate_forensics import CalibrationError, calibrate


def _results(tmp_path, *, both_labels=True):
    labels = [False, True] if both_labels else [False, False]
    rows = [{
        "id": f"item-{index}",
        "status": "ok",
        "split": "validation",
        "group_id": f"source-{index}",
        "expected_detection": expected,
        "signal_scores": {
            "ELA": 0.01 if not expected else 0.2,
            "Noise residual": 0.01 if not expected else 0.2,
            "Copy-move": 0.1 if not expected else 0.9,
        },
    } for index, expected in enumerate(labels)]
    path = tmp_path / "results.json"
    path.write_text(json.dumps({"observations": rows}), encoding="utf-8")
    return path


def test_calibration_proposes_without_mutating_production(tmp_path):
    result = calibrate(_results(tmp_path), tmp_path / "calibration.json")

    assert result["validation_source_group_count"] == 2
    assert result["proposals"]["ELA"]["proposed_detection_threshold"] == 0.2
    assert json.loads((tmp_path / "calibration.json").read_text())["schema_version"] == "1.0"


def test_calibration_rejects_single_class_validation(tmp_path):
    with pytest.raises(CalibrationError, match="both authentic and edited"):
        calibrate(_results(tmp_path, both_labels=False), tmp_path / "out.json")
