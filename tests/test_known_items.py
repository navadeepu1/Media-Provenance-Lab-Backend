from io import BytesIO

from PIL import Image

from app import known_items
from app.config import settings


def test_hashes_match_recompressed_reference(monkeypatch, tmp_path):
    from app.db import init_db

    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'known.db'}")
    init_db()
    image = Image.new("RGB", (320, 320), (80, 120, 160))
    item_id = f"fixture-{tmp_path.name}"
    known_items.seed(item_id, "Fixture", "Synthetic reference", image)
    recompressed = Image.open(BytesIO(_jpeg(image, 65)))
    matches = known_items.match(recompressed)
    matched = next(item for item in matches if item["id"] == item_id)
    assert matched["phash_distance"] <= settings.known_item_phash_threshold


def test_unrelated_image_does_not_match(monkeypatch, tmp_path):
    from app.db import init_db

    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'known.db'}")
    init_db()
    reference = Image.new("RGB", (320, 320), "white")
    for x in range(0, 320, 32):
        for y in range(0, 320, 32):
            if (x // 32 + y // 32) % 2:
                reference.paste("black", (x, y, x + 32, y + 32))
    item_id = f"fixture-{tmp_path.name}"
    known_items.seed(item_id, "Fixture", "Synthetic reference", reference)
    unrelated = Image.new("RGB", (320, 320), "gray")
    assert not any(item["id"] == item_id for item in known_items.match(unrelated))


def test_hashes_bound_large_images(monkeypatch):
    from app.known_items import hashes

    image = Image.new("RGB", (5000, 4000), "blue")
    observed = {}

    def fake_phash(value):
        observed["size"] = value.size
        return "0" * 16

    monkeypatch.setattr(known_items.imagehash, "phash", fake_phash)
    monkeypatch.setattr(known_items.imagehash, "dhash", fake_phash)
    hashes(image)

    assert max(observed["size"]) <= 1024


def _jpeg(image: Image.Image, quality: int) -> bytes:
    output = BytesIO()
    image.save(output, "JPEG", quality=quality)
    return output.getvalue()
