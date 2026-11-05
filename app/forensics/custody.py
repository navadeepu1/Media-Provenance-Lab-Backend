"""HMAC-backed custody verification for investigation v2."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from ..config import settings
from ..db import SessionLocal
from .persistence import CustodyEntryRow


def _key() -> bytes:
    if not settings.custody_hmac_key:
        if settings.app_env == "production":
            raise RuntimeError("CUSTODY_HMAC_KEY is required in production.")
        return b"development-only-custody-key"
    return settings.custody_hmac_key.encode("utf-8")


def _hash(entry: dict[str, Any], previous: str) -> str:
    payload = json.dumps(entry, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hmac.new(_key(), payload + previous.encode(), hashlib.sha256).hexdigest()


def append(tenant_id: str, evidence_id: str, action: str, sha256: str,
           actor_id: str = "local-user") -> dict[str, str]:
    with SessionLocal.begin() as session:
        previous_row = session.scalar(select(CustodyEntryRow).where(
            CustodyEntryRow.tenant_id == tenant_id,
            CustodyEntryRow.evidence_id == evidence_id,
        ).order_by(CustodyEntryRow.created_at.desc()))
        previous = previous_row.entry_hash if previous_row else "0" * 64
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        entry = {"tenant_id": tenant_id, "evidence_id": evidence_id, "action": action,
                 "sha256": sha256, "actor_id": actor_id, "created_at": now.isoformat()}
        digest = _hash(entry, previous)
        session.add(CustodyEntryRow(
            id=hashlib.sha256(f"{evidence_id}:{now.isoformat()}".encode()).hexdigest()[:80],
            tenant_id=tenant_id, evidence_id=evidence_id, action=action,
            prev_hash=previous, entry_hash=digest, payload=json.dumps(entry, sort_keys=True),
            created_at=now,
        ))
        return {"entry_hash": digest, "prev_hash": previous}


def verify(tenant_id: str, evidence_id: str | None = None) -> dict[str, Any]:
    with SessionLocal() as session:
        query = select(CustodyEntryRow).where(CustodyEntryRow.tenant_id == tenant_id)
        if evidence_id:
            query = query.where(CustodyEntryRow.evidence_id == evidence_id)
        rows = session.scalars(query.order_by(CustodyEntryRow.created_at.asc())).all()
    previous = "0" * 64
    broken = None
    for index, row in enumerate(rows):
        payload = json.loads(row.payload)
        expected = _hash(payload, row.prev_hash)
        if row.prev_hash != previous or row.entry_hash != expected:
            broken = index
            break
        previous = row.entry_hash
    return {"valid": broken is None, "entry_count": len(rows),
            "head_hash": previous if rows else None, "first_broken_index": broken}
