"""Strict normalized models for investigation API v2."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Action(str, Enum):
    logon_success = "logon_success"
    logon_failure = "logon_failure"
    logoff = "logoff"
    privilege_granted = "privilege_granted"
    privilege_used = "privilege_used"
    file_read = "file_read"
    file_write = "file_write"
    file_delete = "file_delete"
    file_create = "file_create"
    process_start = "process_start"
    network_connection = "network_connection"
    web_visit = "web_visit"
    config_change = "config_change"
    account_created = "account_created"
    account_deleted = "account_deleted"
    service_stopped = "service_stopped"
    unknown = "unknown"


class NormalizedEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    tenant_id: str
    case_id: str
    evidence_id: str
    source_type: str
    timestamp_utc: datetime
    tz_original: str | None = None
    timezone_assumed: bool = False
    actor: str | None = None
    host: str | None = None
    action: Action
    object: str | None = None
    outcome: str | None = None
    source_ip: str | None = None
    geo_country: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    raw_ref: str
    raw_text: str = Field(max_length=2000)
    parse_warning: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    tenant_id: str
    case_id: str
    rule_id: str
    title: str
    severity: str
    confidence: float = Field(ge=0, le=1)
    event_ids: list[str] = Field(min_length=1)
    actor: str | None = None
    host: str | None = None
    window_start: datetime
    window_end: datetime
    explanation: str
    limitations: list[str] = Field(default_factory=list)
    status: str = "new"


class CaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)


class CaseStatusChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str
    reason: str | None = Field(default=None, max_length=2000)


class NoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=10000)


class TagCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.:-]+$")


class BookmarkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str | None = None
    finding_id: str | None = None


class FindingStatusChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str
    reason: str | None = Field(default=None, max_length=2000)
