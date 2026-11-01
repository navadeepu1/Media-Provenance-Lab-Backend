"""Optional C2PA capability and manifest inspection.

The official ``c2pa-python`` binding is optional because native wheels are not
available for every deployment target. Reports distinguish unavailable,
absent, invalid, and present manifests instead of treating absence as proof.
"""

from __future__ import annotations

import importlib
import tempfile
from pathlib import Path
from typing import Any


def capability() -> str:
    try:
        module = importlib.import_module("c2pa")
    except ImportError:
        return "unavailable"
    return "available" if hasattr(module, "Reader") else "unavailable"


def inspect_bytes(raw: bytes, suffix: str) -> dict[str, Any]:
    status = capability()
    result: dict[str, Any] = {
        "capability": status,
        "status": "not_checked" if status == "unavailable" else "absent",
        "manifest_count": 0,
    }
    if status == "unavailable":
        result["reason"] = "The optional c2pa-python binding is not installed."
        return result

    try:
        module = importlib.import_module("c2pa")
        with tempfile.TemporaryDirectory(prefix="mpl-c2pa-") as directory:
            path = Path(directory) / f"input{suffix}"
            path.write_bytes(raw)
            store = module.Reader(str(path)).read()
        if not store:
            return result
        result["status"] = "present"
        result["manifest_count"] = len(store.get("manifests", {})) if isinstance(store, dict) else 1
        return result
    except Exception as exc:
        result["status"] = "invalid"
        result["reason"] = f"C2PA manifest inspection failed: {type(exc).__name__}."
        return result
