"""Upload/report artifact storage.

The local backend is intentionally explicit. Production deployments should use
an authenticated, private S3-compatible backend and keep only object keys in
the database.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from .config import settings


class StorageError(RuntimeError):
    """Storage is unavailable or an artifact cannot be read."""


def backend_status() -> str:
    return settings.storage_backend if settings.storage_backend in {"local", "s3"} else "invalid"


def _root() -> Path:
    root = Path(settings.storage_root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _path(key: str) -> Path:
    root = _root().resolve()
    path = (root / key).resolve()
    if root not in path.parents:
        raise StorageError("Invalid artifact key.")
    return path


def put_bytes(data: bytes, category: str, key: str | None = None) -> str:
    if backend_status() != "local":
        raise StorageError("S3 storage is not configured in this build.")
    safe_key = key or hashlib.sha256(data).hexdigest()
    path = _path(f"{category}/{safe_key}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return f"{category}/{safe_key}"


def read_bytes(key: str) -> bytes:
    if backend_status() != "local":
        raise StorageError("S3 storage is not configured in this build.")
    path = _path(key)
    if not path.is_file():
        raise StorageError("Artifact is unavailable.")
    return path.read_bytes()


def delete(key: str) -> bool:
    if backend_status() != "local":
        raise StorageError("S3 storage is not configured in this build.")
    path = _path(key)
    if not path.is_file():
        return False
    path.unlink()
    return True


def secure_delete(key: str) -> bool:
    if backend_status() != "local":
        raise StorageError("Secure local deletion is unavailable for non-local storage.")
    path = _path(key)
    if not path.is_file():
        return False
    size = path.stat().st_size
    with path.open("r+b") as handle:
        handle.write(b"\x00" * size)
        handle.flush()
    path.unlink()
    return True
