import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


class JobRow(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    current_module: Mapped[str] = mapped_column(String(80), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    report_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_path: Mapped[str] = mapped_column(Text)
    demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ReportRow(Base):
    __tablename__ = "reports"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(80))
    payload: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime] = mapped_column(DateTime)


def _engine():
    url = settings.database_url
    if url.startswith("sqlite:///"):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})


engine = _engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def recover_interrupted_jobs() -> int:
    with SessionLocal.begin() as session:
        rows = session.scalars(select(JobRow).where(JobRow.status.in_(("queued", "running")))).all()
        for row in rows:
            row.status = "failed"
            row.error_code = "interrupted"
            row.error_message = "This report was lost when the free server restarted."
            row.finished_at = _now()
        return len(rows)


def create_job(job_id: str, raw_path: Path, demo: bool) -> None:
    with SessionLocal.begin() as session:
        session.add(JobRow(id=job_id, raw_path=str(raw_path), demo=demo))


def update_job(job_id: str, **values: Any) -> None:
    with SessionLocal.begin() as session:
        row = session.get(JobRow, job_id)
        if row:
            for key, value in values.items():
                setattr(row, key, value)


def job_dict(job_id: str) -> dict[str, Any] | None:
    with SessionLocal() as session:
        row = session.get(JobRow, job_id)
        if not row:
            return None
        return {key: getattr(row, key) for key in
                ("id", "status", "current_module", "progress", "report_id", "error_code", "error_message")}


def save_report(report: dict[str, Any], job_id: str) -> None:
    now = _now()
    with SessionLocal.begin() as session:
        session.add(ReportRow(id=report["report_id"], job_id=job_id,
                              payload=json.dumps(report), created_at=now,
                              expires_at=now + timedelta(days=30)))


def load_report(report_id: str) -> dict[str, Any] | None:
    with SessionLocal() as session:
        row = session.get(ReportRow, report_id)
        if not row or row.expires_at < _now():
            return None
        return json.loads(row.payload)


def cleanup_expired() -> dict[str, int]:
    now = _now()
    with SessionLocal.begin() as session:
        reports = session.scalars(select(ReportRow).where(ReportRow.expires_at < now)).all()
        jobs = session.scalars(select(JobRow).where(JobRow.created_at < now - timedelta(days=1))).all()
        for row in reports:
            session.delete(row)
        for row in jobs:
            path = Path(row.raw_path)
            if path.is_file():
                path.unlink()
            session.delete(row)
        return {"reports": len(reports), "uploads": len(jobs)}
