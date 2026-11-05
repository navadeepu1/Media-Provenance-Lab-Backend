"""Tenant-scoped persistence for investigation platform v2."""

from __future__ import annotations

import json
import uuid
import base64
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base, SessionLocal
from .models import Finding, NormalizedEvent


class V2EventRow(Base):
    __tablename__ = "v2_events"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(120), index=True)
    case_id: Mapped[str] = mapped_column(String(80), index=True)
    evidence_id: Mapped[str] = mapped_column(String(80), index=True)
    source_type: Mapped[str] = mapped_column(String(80))
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime, index=True)
    payload: Mapped[str] = mapped_column(Text)
    raw_text: Mapped[str] = mapped_column(Text)

    __table_args__ = (
        Index("ix_v2_event_tenant_case_time", "tenant_id", "case_id", "timestamp_utc"),
        Index("ix_v2_event_tenant_actor", "tenant_id", "payload"),
    )


class TenantRow(Base):
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime)


class UserRow(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(120), index=True)
    external_subject: Mapped[str] = mapped_column(String(255), index=True)
    role: Mapped[str] = mapped_column(String(30), default="viewer")
    created_at: Mapped[datetime] = mapped_column(DateTime)


class CaseV2Row(Base):
    __tablename__ = "cases"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(120), index=True)
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime)


class EvidenceV2Row(Base):
    __tablename__ = "evidence"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(120), index=True)
    case_id: Mapped[str] = mapped_column(String(80), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    mime: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    parser: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30), default="active")
    scan_status: Mapped[str] = mapped_column(String(30), default="not_scanned")
    uploader: Mapped[str] = mapped_column(String(120))
    storage_key: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class IncidentRow(Base):
    __tablename__ = "incidents"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(120), index=True)
    case_id: Mapped[str] = mapped_column(String(80), index=True)
    start_at: Mapped[datetime] = mapped_column(DateTime)
    end_at: Mapped[datetime] = mapped_column(DateTime)
    payload: Mapped[str] = mapped_column(Text)


class NoteRow(Base):
    __tablename__ = "notes"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(120), index=True)
    case_id: Mapped[str] = mapped_column(String(80), index=True)
    author_id: Mapped[str] = mapped_column(String(120))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class TagRow(Base):
    __tablename__ = "tags"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(120), index=True)
    case_id: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(80))


class BookmarkRow(Base):
    __tablename__ = "bookmarks"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(120), index=True)
    case_id: Mapped[str] = mapped_column(String(80), index=True)
    event_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    finding_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class CustodyEntryRow(Base):
    __tablename__ = "custody_entries"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(120), index=True)
    evidence_id: Mapped[str] = mapped_column(String(80), index=True)
    action: Mapped[str] = mapped_column(String(80))
    prev_hash: Mapped[str] = mapped_column(String(64))
    entry_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime)


class AuditLogRow(Base):
    __tablename__ = "audit_log"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(120), index=True)
    actor_id: Mapped[str] = mapped_column(String(120))
    action: Mapped[str] = mapped_column(String(100))
    payload: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class AiSummaryRow(Base):
    __tablename__ = "ai_summaries"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(120), index=True)
    case_id: Mapped[str] = mapped_column(String(80), index=True)
    input_hash: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(40))
    text: Mapped[str] = mapped_column(Text)
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class V2FindingRow(Base):
    __tablename__ = "v2_findings"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(120), index=True)
    case_id: Mapped[str] = mapped_column(String(80), index=True)
    rule_id: Mapped[str] = mapped_column(String(80), index=True)
    severity: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="new")
    payload: Mapped[str] = mapped_column(Text)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _serialize(row: Any) -> dict[str, Any]:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def ensure_case(tenant_id: str, case_id: str, title: str | None = None) -> dict[str, Any]:
    with SessionLocal.begin() as session:
        row = session.scalar(select(CaseV2Row).where(
            CaseV2Row.tenant_id == tenant_id, CaseV2Row.id == case_id
        ))
        if not row:
            row = CaseV2Row(id=case_id, tenant_id=tenant_id, title=title or case_id,
                            status="open", created_at=_now())
            session.add(row)
        return _serialize(row)


def create_case(tenant_id: str, title: str) -> dict[str, Any]:
    case_id = uuid.uuid4().hex
    return ensure_case(tenant_id, case_id, title)


def list_cases(tenant_id: str) -> list[dict[str, Any]]:
    with SessionLocal() as session:
        rows = session.scalars(select(CaseV2Row).where(
            CaseV2Row.tenant_id == tenant_id
        ).order_by(CaseV2Row.created_at.desc(), CaseV2Row.id.asc())).all()
        return [_serialize(row) for row in rows]


def get_case(tenant_id: str, case_id: str) -> dict[str, Any] | None:
    with SessionLocal() as session:
        row = session.scalar(select(CaseV2Row).where(
            CaseV2Row.tenant_id == tenant_id, CaseV2Row.id == case_id
        ))
        return _serialize(row) if row else None


def change_case_status(tenant_id: str, case_id: str, status: str, reason: str | None) -> dict[str, Any] | None:
    allowed = {"open": {"in_review"}, "in_review": {"closed"}, "closed": {"open"}}
    if status not in {"open", "in_review", "closed"}:
        raise ValueError("Invalid case status.")
    with SessionLocal.begin() as session:
        row = session.scalar(select(CaseV2Row).where(
            CaseV2Row.tenant_id == tenant_id, CaseV2Row.id == case_id
        ))
        if not row:
            return None
        if status not in allowed.get(row.status, set()):
            raise ValueError(f"Cannot change case status from {row.status} to {status}.")
        if row.status == "closed" and (status != "open" or not reason or not reason.strip()):
            raise ValueError("Reopening a closed case requires a reason.")
        row.status = status
        return _serialize(row)


def save_evidence(tenant_id: str, case_id: str, evidence_id: str, filename: str,
                  size: int, sha256: str, parser: str, storage_key: str,
                  mime: str = "application/octet-stream") -> dict[str, Any]:
    row = EvidenceV2Row(id=evidence_id, tenant_id=tenant_id, case_id=case_id,
                        filename=filename[:255], size=size, sha256=sha256, mime=mime,
                        parser=parser, status="active", scan_status="not_scanned",
                        uploader=tenant_id, storage_key=storage_key, created_at=_now())
    with SessionLocal.begin() as session:
        session.add(row)
    return _serialize(row)


def list_evidence(tenant_id: str, case_id: str) -> list[dict[str, Any]]:
    with SessionLocal() as session:
        rows = session.scalars(select(EvidenceV2Row).where(
            EvidenceV2Row.tenant_id == tenant_id, EvidenceV2Row.case_id == case_id,
            EvidenceV2Row.status != "deleted"
        ).order_by(EvidenceV2Row.created_at.desc(), EvidenceV2Row.id.asc())).all()
        return [_serialize(row) for row in rows]


def get_evidence(tenant_id: str, evidence_id: str) -> dict[str, Any] | None:
    with SessionLocal() as session:
        row = session.scalar(select(EvidenceV2Row).where(
            EvidenceV2Row.tenant_id == tenant_id, EvidenceV2Row.id == evidence_id,
            EvidenceV2Row.status != "deleted"
        ))
        return _serialize(row) if row else None


def delete_evidence(tenant_id: str, evidence_id: str, hard: bool = False) -> dict[str, Any] | None:
    with SessionLocal.begin() as session:
        row = session.scalar(select(EvidenceV2Row).where(
            EvidenceV2Row.tenant_id == tenant_id, EvidenceV2Row.id == evidence_id
        ))
        if not row or row.status == "deleted":
            return None
        storage_key = row.storage_key
        if hard:
            session.delete(row)
            session.query(V2EventRow).filter(
                V2EventRow.tenant_id == tenant_id, V2EventRow.evidence_id == evidence_id
            ).delete(synchronize_session=False)
        else:
            row.status = "deleted"
        return {"id": evidence_id, "status": "deleted", "hard": hard, "storage_key": storage_key}


def create_note(tenant_id: str, case_id: str, author_id: str, text_value: str) -> dict[str, Any]:
    row = NoteRow(id=uuid.uuid4().hex, tenant_id=tenant_id, case_id=case_id,
                  author_id=author_id, text=text_value, created_at=_now())
    with SessionLocal.begin() as session:
        session.add(row)
    return _serialize(row)


def list_notes(tenant_id: str, case_id: str) -> list[dict[str, Any]]:
    with SessionLocal() as session:
        rows = session.scalars(select(NoteRow).where(
            NoteRow.tenant_id == tenant_id, NoteRow.case_id == case_id
        ).order_by(NoteRow.created_at.asc(), NoteRow.id.asc())).all()
        return [_serialize(row) for row in rows]


def create_tag(tenant_id: str, case_id: str, name: str) -> dict[str, Any]:
    with SessionLocal.begin() as session:
        row = session.scalar(select(TagRow).where(
            TagRow.tenant_id == tenant_id, TagRow.case_id == case_id, TagRow.name == name
        ))
        if not row:
            row = TagRow(id=uuid.uuid4().hex, tenant_id=tenant_id, case_id=case_id, name=name)
            session.add(row)
        return _serialize(row)


def list_tags(tenant_id: str, case_id: str) -> list[dict[str, Any]]:
    with SessionLocal() as session:
        rows = session.scalars(select(TagRow).where(
            TagRow.tenant_id == tenant_id, TagRow.case_id == case_id
        ).order_by(TagRow.name.asc())).all()
        return [_serialize(row) for row in rows]


def create_bookmark(tenant_id: str, case_id: str, event_id: str | None,
                    finding_id: str | None) -> dict[str, Any]:
    if bool(event_id) == bool(finding_id):
        raise ValueError("Provide exactly one event_id or finding_id.")
    with SessionLocal.begin() as session:
        if event_id and not session.scalar(select(V2EventRow).where(
            V2EventRow.tenant_id == tenant_id, V2EventRow.case_id == case_id, V2EventRow.id == event_id
        )):
            raise ValueError("Event not found.")
        if finding_id and not session.scalar(select(V2FindingRow).where(
            V2FindingRow.tenant_id == tenant_id, V2FindingRow.case_id == case_id, V2FindingRow.id == finding_id
        )):
            raise ValueError("Finding not found.")
        row = BookmarkRow(id=uuid.uuid4().hex, tenant_id=tenant_id, case_id=case_id,
                          event_id=event_id, finding_id=finding_id, created_at=_now())
        session.add(row)
        return _serialize(row)


def list_bookmarks(tenant_id: str, case_id: str) -> list[dict[str, Any]]:
    with SessionLocal() as session:
        rows = session.scalars(select(BookmarkRow).where(
            BookmarkRow.tenant_id == tenant_id, BookmarkRow.case_id == case_id
        ).order_by(BookmarkRow.created_at.asc(), BookmarkRow.id.asc())).all()
        return [_serialize(row) for row in rows]


def update_finding_status(tenant_id: str, finding_id: str, status: str,
                          reason: str | None) -> dict[str, Any] | None:
    if status not in {"new", "confirmed", "dismissed"}:
        raise ValueError("Invalid finding status.")
    if status == "dismissed" and not reason:
        raise ValueError("Dismissing a finding requires a reason.")
    with SessionLocal.begin() as session:
        row = session.scalar(select(V2FindingRow).where(
            V2FindingRow.tenant_id == tenant_id, V2FindingRow.id == finding_id
        ))
        if not row:
            return None
        payload = json.loads(row.payload)
        payload["status"] = status
        payload["dismissal_reason"] = reason if status == "dismissed" else None
        row.status = status
        row.payload = json.dumps(payload)
        return payload


def timeline_filtered(tenant_id: str, case_id: str, actor: str | None = None,
                      host: str | None = None, source_type: str | None = None,
                      action: str | None = None, minimum_severity: str | None = None,
                      from_time: datetime | None = None, to_time: datetime | None = None,
                      incident: str | None = None, cursor: str | None = None,
                      limit: int = 100) -> dict[str, Any]:
    events = load_events(tenant_id, case_id)
    findings = load_findings(tenant_id, case_id)
    event_severity = {event_id: finding.severity for finding in findings for event_id in finding.event_ids}
    order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    filtered = []
    for event in events:
        if actor and event.actor != actor or host and event.host != host:
            continue
        if source_type and event.source_type != source_type or action and event.action.value != action:
            continue
        if from_time and event.timestamp_utc < from_time or to_time and event.timestamp_utc > to_time:
            continue
        if minimum_severity and order.get(event_severity.get(event.id, "low"), 0) < order.get(minimum_severity, 0):
            continue
        if incident:
            incident_events = [item["event_ids"] for item in load_incidents(tenant_id, case_id) if item["id"] == incident]
            if not any(event.id in ids for ids in incident_events):
                continue
        filtered.append(event)
    filtered.sort(key=lambda event: (event.timestamp_utc, event.id))
    start = 0
    if cursor:
        try:
            decoded_cursor = base64.urlsafe_b64decode(cursor.encode()).decode()
        except (ValueError, UnicodeDecodeError):
            decoded_cursor = ""
        start = next((index + 1 for index, event in enumerate(filtered)
                      if f"{event.timestamp_utc.isoformat()}|{event.id}" == decoded_cursor), len(filtered))
    page = filtered[start:start + max(1, min(limit, 500))]
    next_cursor = (
        base64.urlsafe_b64encode(
            f"{page[-1].timestamp_utc.isoformat()}|{page[-1].id}".encode()
        ).decode()
        if len(page) == max(1, min(limit, 500)) and start + len(page) < len(filtered)
        else None
    )
    return {"events": page, "next_cursor": next_cursor}


def save_events(events: list[NormalizedEvent]) -> int:
    with SessionLocal.begin() as session:
        for event in events:
            session.merge(V2EventRow(
                id=event.id, tenant_id=event.tenant_id, case_id=event.case_id,
                evidence_id=event.evidence_id, source_type=event.source_type,
                timestamp_utc=event.timestamp_utc.replace(tzinfo=None),
                payload=event.model_dump_json(), raw_text=event.raw_text,
            ))
    return len(events)


def save_findings(findings: list[Finding]) -> int:
    with SessionLocal.begin() as session:
        for finding in findings:
            session.merge(V2FindingRow(
                id=finding.id, tenant_id=finding.tenant_id, case_id=finding.case_id,
                rule_id=finding.rule_id, severity=finding.severity, status=finding.status,
                payload=finding.model_dump_json(),
            ))
    return len(findings)


def load_events(tenant_id: str, case_id: str) -> list[NormalizedEvent]:
    with SessionLocal() as session:
        rows = session.scalars(select(V2EventRow).where(
            V2EventRow.tenant_id == tenant_id, V2EventRow.case_id == case_id
        ).order_by(V2EventRow.timestamp_utc.asc(), V2EventRow.id.asc())).all()
        active = {
            row.id for row in session.scalars(select(EvidenceV2Row).where(
                EvidenceV2Row.tenant_id == tenant_id, EvidenceV2Row.case_id == case_id,
                EvidenceV2Row.status != "deleted"
            )).all()
        }
        return [NormalizedEvent.model_validate_json(row.payload)
                for row in rows if row.evidence_id in active]


def load_findings(tenant_id: str, case_id: str) -> list[Finding]:
    with SessionLocal() as session:
        rows = session.scalars(select(V2FindingRow).where(
            V2FindingRow.tenant_id == tenant_id, V2FindingRow.case_id == case_id
        ).order_by(V2FindingRow.id.asc())).all()
        return [Finding.model_validate_json(row.payload) for row in rows]


def save_incidents(incidents: list[dict[str, Any]], tenant_id: str, case_id: str) -> int:
    from datetime import datetime
    with SessionLocal.begin() as session:
        for incident in incidents:
            session.merge(IncidentRow(
                id=incident["id"], tenant_id=tenant_id, case_id=case_id,
                start_at=datetime.fromisoformat(incident["start"]).replace(tzinfo=None),
                end_at=datetime.fromisoformat(incident["end"]).replace(tzinfo=None),
                payload=json.dumps(incident),
            ))
    return len(incidents)


def load_incidents(tenant_id: str, case_id: str) -> list[dict[str, Any]]:
    with SessionLocal() as session:
        rows = session.scalars(select(IncidentRow).where(
            IncidentRow.tenant_id == tenant_id, IncidentRow.case_id == case_id
        ).order_by(IncidentRow.start_at.asc())).all()
        return [json.loads(row.payload) for row in rows]
