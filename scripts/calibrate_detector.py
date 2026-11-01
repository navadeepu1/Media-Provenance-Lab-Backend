"""Fit detector calibration from a CSV containing score,label columns.

The labels must come from a held-out, licensed evaluation set. This script
does not manufacture labels or claim accuracy without that evidence.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.calibration import fit_platt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    with args.input.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    scores = [float(row["score"]) for row in rows]
    labels = [int(row["label"]) for row in rows]
    scale, offset = fit_platt(scores, labels)
    args.output.write_text(json.dumps({
        "method": "platt",
        "scale": scale,
        "offset": offset,
        "samples": len(rows),
        "source": str(args.input),
    }, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
