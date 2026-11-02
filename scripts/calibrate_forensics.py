"""Propose forensic score thresholds from a labeled validation split.

This report is advisory. It never changes production constants or writes a
calibration file consumed by the application.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

MODULES = {
    "ELA": {"current_weak": 0.02, "current_strong": 0.10},
    "Noise residual": {"current_weak": 0.02, "current_strong": 0.10},
    "Copy-move": {"current_weak": 0.50, "current_strong": 0.80},
}


class CalibrationError(ValueError):
    """The evaluation results cannot support threshold calibration."""


def _read(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CalibrationError(f"Could not read results: {path}") from exc
    if not isinstance(payload.get("observations"), list):
        raise CalibrationError("Results must contain observations.")
    return payload


def _score_metrics(rows: list[dict[str, Any]], threshold: float) -> tuple[float, int, int]:
    positives = [row for row in rows if row["expected_detection"]]
    negatives = [row for row in rows if not row["expected_detection"]]
    tp = sum(row["score"] >= threshold for row in positives)
    tn = sum(row["score"] < threshold for row in negatives)
    balanced = (tp / len(positives) + tn / len(negatives)) / 2
    return balanced, tp, len(negatives) - tn


def _proposal(rows: list[dict[str, Any]], current: dict[str, float]) -> dict[str, Any]:
    candidates = sorted({0.0, 1.0, *(row["score"] for row in rows)})
    best = None
    for threshold in candidates:
        balanced, true_positive, false_positive = _score_metrics(rows, threshold)
        candidate = (balanced, -false_positive, -threshold, threshold, true_positive, false_positive)
        if best is None or candidate > best:
            best = candidate
    assert best is not None
    return {
        "status": "proposal",
        "current_weak": current["current_weak"],
        "current_strong": current["current_strong"],
        "proposed_detection_threshold": round(best[3], 6),
        "validation_balanced_accuracy": round(best[0], 4),
        "validation_true_positive": best[4],
        "validation_false_positive": best[5],
        "positive_score_range": [
            round(min(row["score"] for row in rows if row["expected_detection"]), 6),
            round(max(row["score"] for row in rows if row["expected_detection"]), 6),
        ],
        "negative_score_range": [
            round(min(row["score"] for row in rows if not row["expected_detection"]), 6),
            round(max(row["score"] for row in rows if not row["expected_detection"]), 6),
        ],
    }


def calibrate(results_path: Path, output_path: Path) -> dict[str, Any]:
    payload = _read(results_path)
    rows = [
        row for row in payload["observations"]
        if row.get("status") == "ok" and row.get("split") == "validation"
    ]
    if not rows:
        raise CalibrationError("No successful validation observations were found.")
    if {row.get("expected_detection") for row in rows} != {False, True}:
        raise CalibrationError("Validation split must contain both authentic and edited labels.")
    groups = {row.get("group_id", row["id"]) for row in rows}
    if len(groups) < 2:
        raise CalibrationError("Validation split must contain at least two source groups.")
    proposals = {}
    for name, current in MODULES.items():
        module_rows = [
            {**row, "score": float(row["signal_scores"][name])}
            for row in rows
            if name in row.get("signal_scores", {})
            and math.isfinite(float(row["signal_scores"][name]))
        ]
        if not module_rows or {row["expected_detection"] for row in module_rows} != {False, True}:
            proposals[name] = {"status": "insufficient_scores"}
        else:
            proposals[name] = _proposal(module_rows, current)
    result = {
        "schema_version": "1.0",
        "source_results": str(results_path),
        "validation_count": len(rows),
        "validation_source_group_count": len(groups),
        "proposals": proposals,
        "limitations": [
            "These are advisory per-module score thresholds, not production changes.",
            "Do not calibrate on derived variants whose source group appears in another split.",
            "Review camera, lighting, recompression, crop, and edit diversity before adoption.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=ROOT / "eval" / "real_results.json")
    parser.add_argument("--output", type=Path, default=ROOT / "eval" / "forensic_calibration.json")
    args = parser.parse_args()
    try:
        result = calibrate(args.results, args.output)
    except CalibrationError as exc:
        parser.error(str(exc))
    print(json.dumps({
        "validation_count": result["validation_count"],
        "validation_source_group_count": result["validation_source_group_count"],
        "output": str(args.output),
    }, indent=2))


if __name__ == "__main__":
    main()
