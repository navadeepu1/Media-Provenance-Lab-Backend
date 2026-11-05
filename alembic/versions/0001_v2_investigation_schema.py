"""Create investigation v2 schema."""

from alembic import op
from app.db import Base
from app.forensics.persistence import (
    AiSummaryRow, AuditLogRow, BookmarkRow, CaseV2Row, CustodyEntryRow,
    EvidenceV2Row, IncidentRow, NoteRow, TagRow, TenantRow, UserRow,
    V2EventRow, V2FindingRow,
)

revision = "0001_v2"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    names = {"tenants", "users", "cases", "evidence", "v2_events", "v2_findings",
             "incidents", "notes", "tags", "bookmarks", "custody_entries",
             "audit_log", "ai_summaries"}
    tables = [table for table in Base.metadata.sorted_tables if table.name in names]
    Base.metadata.create_all(bind=op.get_bind(), tables=tables)


def downgrade():
    names = {"tenants", "users", "cases", "evidence", "v2_events", "v2_findings",
             "incidents", "notes", "tags", "bookmarks", "custody_entries",
             "audit_log", "ai_summaries"}
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in names:
            table.drop(op.get_bind(), checkfirst=True)
