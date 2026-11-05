"""Verify that an optional detector has an auditable provenance record."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


REQUIRED = {
    "artifact_sha256",
    "upstream_url",
    "revision",
    "author",
    "model_license",
    "dataset_license",
    "redistribution_permission",
}


def verify(model: Path, record: Path) -> dict[str, object]:
    if not model.is_file():
        raise ValueError(f"Model artifact does not exist: {model}")
    try:
        payload = json.loads(record.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read governance record: {record}") from exc
    missing = REQUIRED - payload.keys()
    if missing:
        raise ValueError(f"Governance record is missing: {', '.join(sorted(missing))}.")
    digest = hashlib.sha256(model.read_bytes()).hexdigest()
    if payload["artifact_sha256"].lower() != digest:
        raise ValueError("Governance artifact_sha256 does not match the model.")
    if not str(payload["upstream_url"]).startswith(("http://", "https://")):
        raise ValueError("upstream_url must be an HTTP(S) URL.")
    if payload["redistribution_permission"] is not True:
        raise ValueError("redistribution_permission must be true before distribution.")
    return {"status": "verified", "sha256": digest, "model": str(model), "record": str(record)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    parser.add_argument("record", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.model, args.record), indent=2))
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
