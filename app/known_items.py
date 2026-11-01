"""Perceptual matching against explicitly seeded, reviewed reference items."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import imagehash
from PIL import Image

from .config import settings
from .db import known_items


def hashes(image: Image.Image) -> tuple[str, str]:
    rgb = image.convert("RGB")
    return str(imagehash.phash(rgb)), str(imagehash.dhash(rgb))


def match(image: Image.Image) -> list[dict[str, Any]]:
    phash, dhash = hashes(image)
    current_phash = imagehash.hex_to_hash(phash)
    current_dhash = imagehash.hex_to_hash(dhash)
    matches: list[dict[str, Any]] = []
    for item in known_items():
        phash_distance = current_phash - imagehash.hex_to_hash(item["phash"])
        dhash_distance = current_dhash - imagehash.hex_to_hash(item["dhash"])
        if (phash_distance <= settings.known_item_phash_threshold
                and dhash_distance <= settings.known_item_dhash_threshold):
            matches.append({
                "id": item["id"],
                "title": item["title"],
                "description": item["description"],
                "source": item["source"],
                "phash_distance": phash_distance,
                "dhash_distance": dhash_distance,
                "thresholds": {
                    "phash": settings.known_item_phash_threshold,
                    "dhash": settings.known_item_dhash_threshold,
                },
            })
    return sorted(matches, key=lambda value: (
        value["phash_distance"] + value["dhash_distance"],
        value["id"],
    ))


def seed(item_id: str, title: str, description: str, image: Image.Image,
         source: str = "synthetic demo") -> None:
    from .db import seed_known_item

    phash, dhash = hashes(image)
    seed_known_item(item_id, title, description, phash, dhash, source)
