"""Privacy, deletion, and audit helpers used by API workflows."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, Integer, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, SessionLocal


class AuditRow(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(80))
    subject_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    actor_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    payload: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


class ReviewRow(Base):
    __tablename__ = "review_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30), default="queued")
    reviewer_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    decision: Mapped[str | None] = mapped_column(String(40), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


def audit(
    event_type: str,
    subject_id: str | None = None,
    actor_id: str | None = None,
    **payload: Any,
) -> None:
    with SessionLocal.begin() as session:
        session.add(
            AuditRow(
                event_type=event_type,
                subject_id=subject_id,
                actor_id=actor_id,
                payload=json.dumps(payload, default=str),
            )
        )


def recent_events(limit: int = 100) -> list[dict[str, Any]]:
    with SessionLocal() as session:
        rows = session.scalars(
            select(AuditRow)
            .order_by(AuditRow.created_at.desc())
            .limit(limit)
        ).all()
        return [
            {
                "event_type": row.event_type,
                "subject_id": row.subject_id,
                "actor_id": row.actor_id,
                "payload": json.loads(row.payload),
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]


def create_review(report_id: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    with SessionLocal.begin() as session:
        row = ReviewRow(report_id=report_id, created_at=now, updated_at=now)
        session.add(row)
        session.flush()
        result = {"id": row.id, "report_id": report_id, "status": row.status}
    audit("review_created", subject_id=report_id, review_id=result["id"])
    return result


def update_review(
    review_id: int,
    status: str,
    decision: str | None,
    notes: str | None,
    reviewer_id: str | None = None,
) -> dict[str, Any] | None:
    with SessionLocal.begin() as session:
        row = session.get(ReviewRow, review_id)
        if not row:
            return None
        row.status = status
        row.decision = decision
        row.notes = notes
        row.reviewer_id = reviewer_id
        row.updated_at = datetime.now(timezone.utc)
        result = {
            "id": row.id,
            "report_id": row.report_id,
            "status": row.status,
            "decision": row.decision,
            "notes": row.notes,
        }
    audit("review_updated", subject_id=result["report_id"], review_id=review_id, status=status)
    return result
