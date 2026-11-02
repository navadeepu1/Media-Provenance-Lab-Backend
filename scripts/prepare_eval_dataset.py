"""Create labeled derived categories from an authentic image folder.

This script creates deterministic recompressed, forwarded, spliced, and
copy-moved examples. It never fabricates AI-generated examples; those must be
added from a separately documented source.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from pathlib import Path

from PIL import Image, ImageEnhance

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
CATEGORIES = ("authentic", "recompressed", "spliced", "copy_moved", "ai_generated", "forwarded")
MAX_DERIVED_SIDE = 2048


def _jpeg_bytes(image: Image.Image, quality: int) -> bytes:
    output = io.BytesIO()
    image.convert("RGB").save(output, "JPEG", quality=quality)
    return output.getvalue()


def _recompressed(image: Image.Image) -> bytes:
    return _jpeg_bytes(image, quality=82)


def _forwarded(image: Image.Image) -> bytes:
    forwarded = ImageEnhance.Contrast(image.convert("RGB")).enhance(0.98)
    return _jpeg_bytes(forwarded, quality=65)


def _spliced(image: Image.Image, donor: Image.Image) -> bytes:
    base = image.convert("RGB").copy()
    width, height = base.size
    patch_width = max(64, width // 5)
    patch_height = max(64, height // 5)
    patch = donor.convert("RGB").resize((patch_width, patch_height), Image.Resampling.BICUBIC)
    base.paste(patch, ((width - patch_width) // 2, (height - patch_height) // 2))
    return _jpeg_bytes(base, quality=90)


def _copy_moved(image: Image.Image) -> bytes:
    base = image.convert("RGB").copy()
    width, height = base.size
    patch_width = max(64, width // 6)
    patch_height = max(64, height // 6)
    left = max(0, (width - patch_width) // 4)
    top = max(0, (height - patch_height) // 4)
    patch = base.crop((left, top, left + patch_width, top + patch_height))
    destination = (width - patch_width - left, height - patch_height - top)
    base.paste(patch, destination)
    return _jpeg_bytes(base, quality=90)


def _write(path: Path, raw: bytes) -> dict[str, object]:
    if not path.exists() or path.read_bytes() != raw:
        path.write_bytes(raw)
    return {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "path": path.name,
    }


def prepare(
    input_dir: Path,
    output_dir: Path,
    *,
    source_type: str,
    license_name: str,
    source: str,
    source_url: str = "not_applicable",
    attribution_requirements: str = "not_applicable",
    download_date: str = "not_applicable",
    consent_record: str = "project contributor consent",
) -> Path:
    sources = sorted(
        path for path in input_dir.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )
    if not sources:
        raise ValueError(f"No supported images found in {input_dir}.")
    if source_type not in {"personal", "open_source"}:
        raise ValueError("source_type must be personal or open_source.")
    if source_type == "open_source":
        if not source_url.startswith(("http://", "https://")):
            raise ValueError("Open-source data requires an HTTP source_url.")
        if download_date == "not_applicable":
            raise ValueError("Open-source data requires --download-date YYYY-MM-DD.")
    if source_type == "personal" and source_url != "not_applicable":
        raise ValueError("Personal data must use source_url=not_applicable.")

    for category in CATEGORIES:
        (output_dir / category).mkdir(parents=True, exist_ok=True)

    manifest_samples: list[dict[str, object]] = []
    for index, path in enumerate(sources):
        with Image.open(path) as image:
            image.load()
            source_raw = path.read_bytes()
            working = image.convert("RGB")
            working.thumbnail((MAX_DERIVED_SIDE, MAX_DERIVED_SIDE), Image.Resampling.LANCZOS)
            donor_path = sources[(index + 1) % len(sources)]
            with Image.open(donor_path) as donor:
                donor.load()
                donor_working = donor.convert("RGB")
                donor_working.thumbnail(
                    (MAX_DERIVED_SIDE, MAX_DERIVED_SIDE), Image.Resampling.LANCZOS
                )
                variants = {
                    "recompressed": _recompressed(working),
                    "forwarded": _forwarded(working),
                }
                raw_variants = {
                    "spliced": _spliced(working, donor_working),
                    "copy_moved": _copy_moved(working),
                }

            for category, raw in variants.items():
                target = output_dir / category / f"{path.stem}.jpg"
                info = _write(target, raw)
                manifest_samples.append(_record(
                    info, target, category, index, path, source_type, license_name, source,
                    source_url, attribution_requirements, download_date, consent_record,
                ))
            for category, raw in raw_variants.items():
                target = output_dir / category / f"{path.stem}.jpg"
                info = _write(target, raw)
                manifest_samples.append(_record(
                    info, target, category, index, path, source_type, license_name, source,
                    source_url, attribution_requirements, download_date, consent_record,
                ))
            target = output_dir / "authentic" / path.name
            info = _write(target, source_raw)
            manifest_samples.append(_record(
                info, target, "authentic", index, path, source_type, license_name, source,
                source_url, attribution_requirements, download_date, consent_record,
            ))
            working.close()
            donor_working.close()

    manifest = {
        "schema_version": "1.0",
        "dataset_id": "mpl-real-derived-v1",
        "purpose": "Derived regression examples from documented source images.",
        "samples": manifest_samples,
        "notices": [
            "Derived transformations are not human ground truth for all forensic tasks.",
            "The ai_generated category is intentionally empty until independently sourced files are documented.",
        ],
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def _record(
    info, target, category, index, source_path, source_type, license_name, source,
    source_url, attribution_requirements, download_date, consent_record,
):
    return {
        "id": f"{category}-{source_path.stem}",
        "path": str(target.relative_to(target.parents[1])).replace("\\", "/"),
        "sha256": info["sha256"],
        "label": category,
        "expected_detection": category != "authentic",
        "source_type": source_type,
        "license": license_name,
        "source": source,
        "source_url": source_url,
        "attribution_requirements": attribution_requirements,
        "download_date": download_date,
        "modification_history": [
            "Original source file retained for authentic category.",
            f"Derived as {category} for evaluation."
            if category != "authentic" else "No modification; source file copied unchanged.",
        ],
        "consent_record": consent_record if source_type == "personal" else "not_applicable",
        "split": ("train", "validation", "test")[index % 3],
        "derived_from": str(source_path).replace("\\", "/"),
        "group_id": source_path.stem,
        "transformation": category,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "eval_data" / "authentic")
    parser.add_argument("--output", type=Path, default=ROOT / "eval_data")
    parser.add_argument("--source-type", choices=("personal", "open_source"), required=True)
    parser.add_argument("--license", required=True, dest="license_name")
    parser.add_argument("--source", required=True)
    parser.add_argument("--source-url", default="not_applicable")
    parser.add_argument("--attribution-requirements", default="not_applicable")
    parser.add_argument("--download-date", default="not_applicable")
    parser.add_argument("--consent-record", default="project contributor consent")
    args = parser.parse_args()
    manifest = prepare(
        args.input, args.output, source_type=args.source_type,
        license_name=args.license_name,         source=args.source, source_url=args.source_url,
        attribution_requirements=args.attribution_requirements,
        download_date=args.download_date, consent_record=args.consent_record,
    )
    print(f"Wrote {manifest}")


if __name__ == "__main__":
    main()
