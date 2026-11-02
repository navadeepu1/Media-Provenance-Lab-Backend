import json
from pathlib import Path

from PIL import Image

from scripts.prepare_eval_dataset import CATEGORIES, prepare


def test_prepare_creates_derived_categories_and_manifest(tmp_path):
    source = tmp_path / "authentic"
    source.mkdir()
    Image.new("RGB", (640, 480), "navy").save(source / "one.jpg", "JPEG")
    output = tmp_path / "dataset"

    manifest_path = prepare(
        source,
        output,
        source_type="personal",
        license_name="private-consented",
        source="test fixture",
    )

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert {item["label"] for item in payload["samples"]} == {
        "authentic", "recompressed", "forwarded", "spliced", "copy_moved",
    }
    assert all((output / category).is_dir() for category in CATEGORIES)
    assert not list((output / "ai_generated").iterdir())
    assert all("sha256" in item and item["source_type"] == "personal" for item in payload["samples"])
    assert all(item["source_url"] == "not_applicable" for item in payload["samples"])
    assert all(item["modification_history"] for item in payload["samples"])
