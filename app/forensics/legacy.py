"""Offline-first evidence ingestion and investigation timeline helpers."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import sqlite3
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column

from ..config import settings
from ..db import Base, SessionLocal
from ..privacy import audit


class CaseRow(Base):
    __tablename__ = "forensic_cases"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="open")
    owner_id: Mapped[str] = mapped_column(String(120), default="local-user")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class EvidenceRow(Base):
    __tablename__ = "forensic_evidence"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("forensic_cases.id"))
    name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(40))
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(Integer)
    stored_path: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class TimelineEventRow(Base):
    __tablename__ = "forensic_timeline_events"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("forensic_cases.id"))
    evidence_id: Mapped[str] = mapped_column(ForeignKey("forensic_evidence.id"))
    event_time: Mapped[datetime] = mapped_column(DateTime)
    event_type: Mapped[str] = mapped_column(String(100))
    actor: Mapped[str] = mapped_column(String(255), default="")
    source: Mapped[str] = mapped_column(String(255), default="")
    summary: Mapped[str] = mapped_column(Text)
    details_json: Mapped[str] = mapped_column(Text, default="{}")


class CustodyRow(Base):
    __tablename__ = "forensic_custody_events"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("forensic_cases.id"))
    evidence_id: Mapped[str] = mapped_column(ForeignKey("forensic_evidence.id"))
    action: Mapped[str] = mapped_column(String(80))
    actor: Mapped[str] = mapped_column(String(120), default="local-user")
    previous_hash: Mapped[str] = mapped_column(String(64))
    event_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


_TIMESTAMP_KEYS = ("timestamp", "time", "event_time", "datetime", "created_at", "date")
_TYPE_KEYS = ("event_type", "event", "action", "type", "operation")
_ACTOR_KEYS = ("actor", "user", "username", "principal", "account")
_TIMESTAMP_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}[T ][0-9:.+-]+(?:Z)?\b")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_time(value: Any) -> datetime:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc).replace(tzinfo=None)
    if isinstance(value, str):
        candidate = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(candidate)
            return (parsed if parsed.tzinfo is None else parsed.astimezone(timezone.utc)).replace(tzinfo=None)
        except ValueError:
            pass
    return _now()


def _first(record: dict[str, Any], keys: tuple[str, ...], default: str = "") -> str:
    for key in keys:
        value = record.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return default


def _records(raw: bytes, kind: str) -> list[dict[str, Any]]:
    if kind == "browser_history":
        with tempfile.NamedTemporaryFile(suffix=".db") as handle:
            handle.write(raw)
            handle.flush()
            connection = sqlite3.connect(handle.name)
            try:
                tables = {row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )}
                if "urls" not in tables:
                    raise ValueError("Browser history database does not contain a urls table.")
                rows = connection.execute(
                    "SELECT url, title, last_visit_time, visit_count FROM urls"
                ).fetchall()
            except sqlite3.DatabaseError as exc:
                raise ValueError("Browser history evidence is not a valid SQLite database.") from exc
            finally:
                connection.close()
        return [
            {"timestamp": datetime.fromtimestamp(
                (int(row[2]) / 1_000_000) - 11644473600, timezone.utc
            ).isoformat() if row[2] else None,
             "event_type": "browser_visit", "source": row[0],
             "summary": f"{row[1] or row[0]} (visits: {row[3] or 0})"}
            for row in rows
        ]
    if kind in {"json", "filesystem_metadata", "application_access"}:
        text = raw.decode("utf-8-sig")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            if kind != "json":
                raise ValueError("JSON evidence must contain valid JSON.")
            payload = [json.loads(line) for line in text.splitlines() if line.strip()]
        if isinstance(payload, dict):
            for key in ("events", "records", "entries", "items"):
                if isinstance(payload.get(key), list):
                    payload = payload[key]
                    break
            else:
                payload = [payload]
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            raise ValueError("JSON evidence must contain an object or an array of objects.")
        return payload
    if kind == "csv":
        return [dict(row) for row in csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))]
    if kind in {"text_logs", "application_access"}:
        records = []
        for line in raw.decode("utf-8-sig", errors="replace").splitlines():
            if not line.strip():
                continue
            match = _TIMESTAMP_RE.search(line)
            records.append({
                "timestamp": match.group(0) if match else None,
                "event_type": "log",
                "summary": line[:2000],
            })
        return records
    raise ValueError("Unsupported evidence kind.")


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _append_custody(session, case_id: str, evidence_id: str, action: str) -> None:
    previous = session.scalar(
        select(CustodyRow).where(CustodyRow.evidence_id == evidence_id).order_by(CustodyRow.created_at.desc())
    )
    previous_hash = previous.event_hash if previous else "0" * 64
    created_at = _now()
    payload = {
        "case_id": case_id, "evidence_id": evidence_id, "action": action,
        "actor": "local-user", "created_at": created_at.isoformat(), "previous_hash": previous_hash,
    }
    event_hash = hashlib.sha256(_canonical(payload)).hexdigest()
    session.add(CustodyRow(
        id=uuid.uuid4().hex, case_id=case_id, evidence_id=evidence_id, action=action,
        actor="local-user", previous_hash=previous_hash, event_hash=event_hash, created_at=created_at,
    ))


def create_case(title: str, description: str = "", owner_id: str = "local-user") -> dict[str, Any]:
    title = title.strip()
    if not title:
        raise ValueError("Case title is required.")
    case_id = uuid.uuid4().hex
    with SessionLocal.begin() as session:
        session.add(CaseRow(id=case_id, title=title[:200], description=description[:5000], owner_id=owner_id))
    audit("forensic_case_created", subject_id=case_id, title=title[:200])
    return {"id": case_id, "title": title[:200], "description": description[:5000], "status": "open", "owner_id": owner_id}


def list_cases() -> list[dict[str, Any]]:
    with SessionLocal() as session:
        rows = session.scalars(select(CaseRow).order_by(CaseRow.created_at.desc())).all()
        return [{"id": row.id, "title": row.title, "description": row.description,
                 "status": row.status, "owner_id": row.owner_id,
                 "created_at": row.created_at.isoformat()} for row in rows]


def owns_case(case_id: str, owner_id: str) -> bool:
    with SessionLocal() as session:
        row = session.get(CaseRow, case_id)
        return bool(row and row.owner_id == owner_id)


def ingest_evidence(case_id: str, name: str, kind: str, raw: bytes) -> dict[str, Any]:
    valid_kinds = {"json", "csv", "text_logs", "filesystem_metadata", "browser_history", "application_access"}
    if kind not in valid_kinds:
        raise ValueError("Evidence kind must be json, csv, text_logs, filesystem_metadata, browser_history, or application_access.")
    if not raw:
        raise ValueError("Evidence file is empty.")
    with SessionLocal() as session:
        if not session.get(CaseRow, case_id):
            raise ValueError("Case was not found.")
    records = _records(raw, kind)
    evidence_id = uuid.uuid4().hex
    digest = hashlib.sha256(raw).hexdigest()
    target_dir = settings.data_dir / "forensics" / case_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{evidence_id}.bin"
    target.write_bytes(raw)
    with SessionLocal.begin() as session:
        evidence = EvidenceRow(
            id=evidence_id, case_id=case_id, name=name[:255], kind=kind,
            sha256=digest, size=len(raw), stored_path=str(target), metadata_json=json.dumps({"record_count": len(records)}),
        )
        session.add(evidence)
        _append_custody(session, case_id, evidence_id, "collected")
        for record in records:
            event_type = _first(record, _TYPE_KEYS, "observation")
            actor = _first(record, _ACTOR_KEYS)
            timestamp = _parse_time(_first(record, _TIMESTAMP_KEYS))
            summary = str(record.get("summary") or record.get("message") or
                          f"{event_type} observed" + (f" by {actor}" if actor else ""))[:4000]
            source = _first(record, ("source", "host", "hostname", "path"), name)[:255]
            session.add(TimelineEventRow(
                id=uuid.uuid4().hex, case_id=case_id, evidence_id=evidence_id,
                event_time=timestamp, event_type=event_type[:100], actor=actor[:255],
                source=source, summary=summary, details_json=json.dumps(record, default=str),
            ))
    audit("forensic_evidence_ingested", subject_id=evidence_id, case_id=case_id,
          kind=kind, sha256=digest, record_count=len(records))
    return {"id": evidence_id, "case_id": case_id, "name": name, "kind": kind,
            "sha256": digest, "size": len(raw), "record_count": len(records)}


def timeline(case_id: str, query: str = "") -> list[dict[str, Any]]:
    with SessionLocal() as session:
        rows = session.scalars(select(TimelineEventRow).where(
            TimelineEventRow.case_id == case_id
        ).order_by(TimelineEventRow.event_time.asc())).all()
        needle = query.strip().lower()
        result = []
        for row in rows:
            haystack = f"{row.event_type} {row.actor} {row.source} {row.summary}".lower()
            if needle and needle not in haystack:
                continue
            result.append({
                "id": row.id, "evidence_id": row.evidence_id, "event_time": row.event_time.isoformat(),
                "event_type": row.event_type, "actor": row.actor, "source": row.source,
                "summary": row.summary, "details": json.loads(row.details_json),
            })
        return result


def suspicious_activity(case_id: str) -> list[dict[str, Any]]:
    events = timeline(case_id)
    findings: list[dict[str, Any]] = []
    for event in events:
        text = f"{event['event_type']} {event['summary']}".lower()
        severity = "medium"
        reason = None
        if any(term in text for term in ("privilege", "admin", "root", "role.grant", "sudo")):
            severity, reason = "high", "Privilege or administrative activity requires review."
        elif any(term in text for term in ("delete", "remove", "purge", "clear log", "disable audit")):
            severity, reason = "high", "Destructive or audit-evasion activity was observed."
        elif any(term in text for term in ("failed login", "authentication failure", "access denied", "denied")):
            severity, reason = "medium", "An authentication or access failure was observed."
        elif event["event_type"].lower() in {"browser_visit", "access", "file_access"}:
            reason = "Access activity was imported and should be correlated with surrounding events."
        if reason:
            findings.append({
                "id": f"finding-{event['id']}", "severity": severity, "confidence": 0.8 if severity == "high" else 0.65,
                "reason": reason, "event_ids": [event["id"]], "event_time": event["event_time"],
                "summary": event["summary"],
            })
    return findings


def assistant_answer(case_id: str, question: str) -> dict[str, Any]:
    question = question.strip()
    if not question:
        raise ValueError("Question is required.")
    tokens = {token.lower() for token in re.findall(r"[a-zA-Z0-9_]{3,}", question)}
    events = timeline(case_id)
    matches = [
        event for event in events
        if not tokens or tokens.intersection({
            token.lower() for token in re.findall(
                r"[a-zA-Z0-9_]{3,}",
                f"{event['event_type']} {event['actor']} {event['source']} {event['summary']}",
            )
        })
    ][:8]
    if matches:
        answer = "Evidence-matched events are listed below. This local assistant does not infer facts beyond the imported records."
    else:
        answer = "No imported timeline event matched the question. Add more evidence or use broader terms."
    return {"answer": answer, "citations": [
        {"event_id": event["id"], "evidence_id": event["evidence_id"],
         "event_time": event["event_time"], "summary": event["summary"]}
        for event in matches
    ], "grounded": True}


def verify_custody(case_id: str) -> dict[str, Any]:
    with SessionLocal() as session:
        rows = session.scalars(select(CustodyRow).where(
            CustodyRow.case_id == case_id
        ).order_by(CustodyRow.created_at.asc())).all()
        previous_by_evidence: dict[str, str] = {}
        problems = []
        for row in rows:
            expected_previous = previous_by_evidence.get(row.evidence_id, "0" * 64)
            payload = {
                "case_id": row.case_id, "evidence_id": row.evidence_id, "action": row.action,
                "actor": row.actor, "created_at": row.created_at.isoformat(), "previous_hash": row.previous_hash,
            }
            expected_hash = hashlib.sha256(_canonical(payload)).hexdigest()
            if row.previous_hash != expected_previous or row.event_hash != expected_hash:
                problems.append(row.id)
            previous_by_evidence[row.evidence_id] = row.event_hash
        anchor_path = Path(settings.custody_anchor_path)
        anchors = json.loads(anchor_path.read_text(encoding="utf-8")) if anchor_path.is_file() else {}
        latest = {}
        for row in rows:
            latest[row.evidence_id] = row.event_hash
        anchor_problems = [
            evidence_id for evidence_id, digest in latest.items()
            if evidence_id in anchors and anchors[evidence_id]["event_hash"] != digest
        ]
        return {"valid": not problems and not anchor_problems, "checked": len(rows),
                "problems": problems, "anchor_problems": anchor_problems,
                "anchored": bool(anchors)}


def anchor_custody(case_id: str) -> dict[str, Any]:
    with SessionLocal() as session:
        rows = session.scalars(select(CustodyRow).where(
            CustodyRow.case_id == case_id
        ).order_by(CustodyRow.created_at.asc())).all()
        latest = {}
        for row in rows:
            latest[row.evidence_id] = row.event_hash
    path = Path(settings.custody_anchor_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    anchors = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    timestamp = _now().isoformat()
    for evidence_id, event_hash in latest.items():
        anchors[evidence_id] = {"case_id": case_id, "event_hash": event_hash, "anchored_at": timestamp,
                                "anchor_type": "local_external_file"}
    path.write_text(json.dumps(anchors, indent=2, sort_keys=True), encoding="utf-8")
    audit("forensic_custody_anchored", subject_id=case_id, count=len(latest))
    return {"anchored": len(latest), "anchor_type": "local_external_file", "path": str(path)}
