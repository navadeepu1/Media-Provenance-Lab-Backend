"""Non-throwing parsers for common forensic log formats."""

from __future__ import annotations

import csv
import io
import json
import re
import sqlite3
import tempfile
import xml.etree.ElementTree as ET
import uuid
from datetime import datetime, timezone
from typing import Any

from .models import Action, NormalizedEvent

_ISO = re.compile(r"\b\d{4}-\d\d-\d\d[T ][0-9:.+-]+(?:Z)?\b")
_WEB = re.compile(
    r'(?P<ip>\S+) \S+ \S+ \[(?P<time>[^\]]+)\] "(?P<request>[^"]*)" '
    r"(?P<status>\d{3}) (?P<size>\S+)"
)


def _time(value: Any, year: int | None = None) -> tuple[datetime, str | None, bool]:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc), "UTC", False
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        original = parsed.strftime("%z") or None
        return parsed.astimezone(timezone.utc), original, False
    except ValueError:
        pass
    if year and re.match(r"^[A-Z][a-z]{2} \d{1,2} \d\d:\d\d:\d\d$", text):
        parsed = datetime.strptime(f"{year} {text}", "%Y %b %d %H:%M:%S").replace(tzinfo=timezone.utc)
        return parsed, None, True
    return datetime.fromtimestamp(0, timezone.utc), None, True


def _action(value: Any) -> Action:
    text = str(value or "").lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "login": Action.logon_success, "success": Action.logon_success,
        "failed_login": Action.logon_failure, "authentication_failure": Action.logon_failure,
        "sudo": Action.privilege_used, "privilege_grant": Action.privilege_granted,
        "read": Action.file_read, "write": Action.file_write, "delete": Action.file_delete,
        "visit": Action.web_visit, "http": Action.web_visit,
    }
    return aliases.get(text, Action(text) if text in {item.value for item in Action} else Action.unknown)


def _event(record: dict[str, Any], tenant_id: str, case_id: str, evidence_id: str,
           source_type: str, raw_ref: str, raw_text: str, year: int | None = None) -> NormalizedEvent:
    timestamp, offset, assumed = _time(
        record.get("timestamp") or record.get("time") or record.get("event_time"), year
    )
    return NormalizedEvent(
        id=uuid.uuid4().hex, tenant_id=tenant_id, case_id=case_id, evidence_id=evidence_id,
        source_type=source_type, timestamp_utc=timestamp, tz_original=offset,
        timezone_assumed=assumed, actor=record.get("actor") or record.get("user"),
        host=record.get("host") or record.get("hostname"), action=_action(record.get("action") or record.get("event")),
        object=record.get("object") or record.get("path"), outcome=record.get("outcome"),
        source_ip=record.get("source_ip") or record.get("ip"), raw_ref=raw_ref,
        raw_text=raw_text[:2000], parse_warning="timestamp_assumed" if assumed else None, details=record,
    )


def parse_json_csv(raw: bytes, tenant_id: str, case_id: str, evidence_id: str,
                   kind: str) -> tuple[list[NormalizedEvent], list[dict[str, Any]]]:
    text = raw.decode("utf-8-sig", errors="replace")
    warnings: list[dict[str, Any]] = []
    try:
        records: list[dict[str, Any]]
        if kind == "csv":
            records = [dict(row) for row in csv.DictReader(io.StringIO(text))]
        else:
            value = json.loads(text)
            records = value if isinstance(value, list) else value.get("events", [value])
        events = [
            _event(record, tenant_id, case_id, evidence_id, kind, str(index + 1), json.dumps(record, default=str))
            for index, record in enumerate(records) if isinstance(record, dict)
        ]
    except (UnicodeError, json.JSONDecodeError, AttributeError, csv.Error) as exc:
        return [], [{"line": 1, "message": f"malformed {kind}: {type(exc).__name__}"}]
    return events, warnings


def parse_linux(raw: bytes, tenant_id: str, case_id: str, evidence_id: str,
                year: int | None = None) -> tuple[list[NormalizedEvent], list[dict[str, Any]]]:
    events: list[NormalizedEvent] = []
    warnings: list[dict[str, Any]] = []
    for line_number, line in enumerate(raw.decode("utf-8", errors="replace").splitlines(), 1):
        match = _ISO.search(line)
        if not match:
            prefix = re.match(r"([A-Z][a-z]{2} \d{1,2} \d\d:\d\d:\d\d)", line)
            if not prefix:
                warnings.append({"line": line_number, "message": "timestamp not recognized"})
                continue
            timestamp = prefix.group(1)
        else:
            timestamp = match.group(0)
        lower = line.lower()
        action = "logon_failure" if "failed password" in lower or "authentication failure" in lower else (
            "logon_success" if "accepted password" in lower else
            "privilege_used" if "sudo:" in lower else "unknown"
        )
        user = re.search(r"(?:for|user=)\s+([A-Za-z0-9_.-]+)", line)
        events.append(_event({"timestamp": timestamp, "action": action, "actor": user.group(1) if user else None,
                              "summary": line}, tenant_id, case_id, evidence_id, "linux_auth", str(line_number), line, year))
    return events, warnings


def parse_web(raw: bytes, tenant_id: str, case_id: str, evidence_id: str) -> tuple[list[NormalizedEvent], list[dict[str, Any]]]:
    events, warnings = [], []
    for line_number, line in enumerate(raw.decode("utf-8", errors="replace").splitlines(), 1):
        match = _WEB.match(line)
        if not match:
            warnings.append({"line": line_number, "message": "not Apache/Nginx combined format"})
            continue
        request = match.group("request").split()
        events.append(_event({"timestamp": datetime.strptime(match.group("time").split()[0], "%d/%b/%Y:%H:%M:%S").replace(tzinfo=timezone.utc).isoformat(),
                              "action": "web_visit", "source_ip": match.group("ip"),
                              "object": request[1] if len(request) > 1 else None,
                              "outcome": match.group("status")}, tenant_id, case_id, evidence_id,
                             "web_access", str(line_number), line))
    return events, warnings


_WINDOWS_ACTIONS = {
    "4624": "logon_success", "4625": "logon_failure", "4672": "privilege_granted",
    "4663": "file_read", "4726": "account_deleted", "4720": "account_created",
}


def parse_windows_xml(raw: bytes, tenant_id: str, case_id: str, evidence_id: str) -> tuple[list[NormalizedEvent], list[dict[str, Any]]]:
    events, warnings = [], []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        return [], [{"line": 1, "message": f"malformed Windows XML: {type(exc).__name__}"}]
    nodes = [root] if root.tag.endswith("Event") else [node for node in root.iter() if node.tag.endswith("Event")]
    for index, node in enumerate(nodes, 1):
        event_id = next((child.text for child in node.iter() if child.tag.endswith("EventID")), None)
        if not event_id:
            warnings.append({"line": index, "message": "missing EventID"})
            continue
        system_time = next((child.attrib.get("SystemTime") for child in node.iter() if child.tag.endswith("TimeCreated")), None)
        provider = next((child.attrib.get("Name") for child in node.iter() if child.tag.endswith("Provider")), None)
        events.append(_event({"timestamp": system_time, "action": _WINDOWS_ACTIONS.get(event_id, "unknown"),
                              "object": provider, "event_id": event_id},
                             tenant_id, case_id, evidence_id, "windows_xml", str(index), ET.tostring(node, encoding="unicode")))
    return events, warnings


def parse_firefox(raw: bytes, tenant_id: str, case_id: str, evidence_id: str) -> tuple[list[NormalizedEvent], list[dict[str, Any]]]:
    warnings: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as directory:
        source = f"{directory}\\places.sqlite"
        with open(source, "wb") as handle:
            handle.write(raw)
        try:
            connection = sqlite3.connect(f"file:{source}?immutable=1&mode=ro", uri=True)
            rows = connection.execute(
                "SELECT p.url, p.title, h.visit_date FROM moz_places p "
                "JOIN moz_historyvisits h ON h.place_id = p.id"
            ).fetchall()
        except (sqlite3.DatabaseError, sqlite3.OperationalError) as exc:
            return [], [{"line": 1, "message": f"invalid Firefox history database: {type(exc).__name__}"}]
        finally:
            if "connection" in locals():
                connection.close()
    events = []
    for index, (url, title, visit_date) in enumerate(rows, 1):
        timestamp = datetime.fromtimestamp((visit_date or 0) / 1_000_000, timezone.utc).isoformat()
        events.append(_event({"timestamp": timestamp, "action": "web_visit", "object": url,
                              "summary": title or url}, tenant_id, case_id, evidence_id,
                             "firefox_history", str(index), f"{url} {title or ''}"))
    return events, warnings
