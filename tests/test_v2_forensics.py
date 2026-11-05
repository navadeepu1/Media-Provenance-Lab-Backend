import json
import uuid

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


def test_v2_json_ingestion_creates_findings_and_tenant_scoped_timeline():
    case_id = f"case-{uuid.uuid4().hex}"
    with TestClient(app) as client:
        response = client.post(
            f"/api/v2/cases/{case_id}/evidence",
            data={"parser": "json"},
            files={"file": ("events.json", json.dumps([
                {"timestamp": "2026-01-01T10:00:00+00:00", "actor": "alice", "host": "laptop",
                 "action": "failed_login"},
                {"timestamp": "2026-01-01T10:01:00+00:00", "actor": "alice", "host": "laptop",
                 "action": "failed_login"},
                {"timestamp": "2026-01-01T10:02:00+00:00", "actor": "alice", "host": "laptop",
                 "action": "failed_login"},
                {"timestamp": "2026-01-01T10:03:00+00:00", "actor": "alice", "host": "laptop",
                 "action": "failed_login"},
                {"timestamp": "2026-01-01T10:04:00+00:00", "actor": "alice", "host": "laptop",
                 "action": "failed_login"},
                {"timestamp": "2026-01-01T10:05:00+00:00", "actor": "alice", "host": "laptop",
                 "action": "login"},
            ]), "application/json")},
        )
        assert response.status_code == 201
        assert response.json()["event_count"] == 6
        findings = client.get(f"/api/v2/cases/{case_id}/findings").json()["findings"]
        assert any(item["rule_id"] == "R-LOGIN-BURST" for item in findings)
        timeline = client.get(f"/api/v2/cases/{case_id}/timeline").json()["events"]
        assert len(timeline) == 6
        assert all(item["tenant_id"] == "local-user" for item in timeline)


def test_v2_malformed_linux_lines_are_warnings_not_crashes():
    with TestClient(app) as client:
        response = client.post(
            "/api/v2/cases/case-b/evidence",
            data={"parser": "linux_auth"},
            files={"file": ("auth.log", b"not a valid line\n", "text/plain")},
        )
        assert response.status_code == 201
        assert response.json()["event_count"] == 0
        assert response.json()["parse_warnings"][0]["line"] == 1


def test_v2_windows_xml_parser_maps_security_events():
    with TestClient(app) as client:
        xml = b"""<Event><System><Provider Name="Security" />
        <EventID>4625</EventID><TimeCreated SystemTime="2026-01-01T10:00:00Z" />
        </System></Event>"""
        response = client.post(
            "/api/v2/cases/windows-case/evidence",
            data={"parser": "windows_xml"},
            files={"file": ("event.xml", xml, "text/xml")},
        )
        assert response.status_code == 201
        assert response.json()["event_count"] == 1
        events = client.get("/api/v2/cases/windows-case/timeline").json()["events"]
        assert events[0]["action"] == "logon_failure"


def test_v2_sequence_and_incident_are_created():
    with TestClient(app) as client:
        records = [
            {"timestamp": "2026-02-01T10:00:00Z", "actor": "bob", "host": "h", "action": "login"},
            {"timestamp": "2026-02-01T10:01:00Z", "actor": "bob", "host": "h", "action": "privilege_granted"},
            {"timestamp": "2026-02-01T10:02:00Z", "actor": "bob", "host": "h", "action": "file_read"},
            {"timestamp": "2026-02-01T10:03:00Z", "actor": "bob", "host": "h", "action": "network_connection"},
        ]
        response = client.post(
            "/api/v2/cases/sequence-case/evidence",
            data={"parser": "json"},
            files={"file": ("sequence.json", json.dumps(records), "application/json")},
        )
        assert response.status_code == 201
        findings = client.get("/api/v2/cases/sequence-case/findings").json()["findings"]
        assert any(item["id"].startswith("SEQ-") for item in findings)
        incidents = client.get("/api/v2/cases/sequence-case/incidents").json()["incidents"]
        assert incidents


def test_v2_custody_is_hmac_verified():
    with TestClient(app) as client:
        response = client.post(
            "/api/v2/cases/custody-case/evidence",
            data={"parser": "json"},
            files={"file": ("event.json", b'{"timestamp":"2026-01-01T00:00:00Z","action":"login"}', "application/json")},
        )
        evidence_id = response.json()["evidence_id"]
        custody = client.get(f"/api/v2/evidence/{evidence_id}/custody")
        assert custody.status_code == 200
        assert custody.json()["valid"] is True
        assert custody.json()["entry_count"] == 1


def test_v2_workflow_crud_transitions_filters_pagination_and_soft_delete():
    with TestClient(app) as client:
        created = client.post("/api/v2/cases", json={"title": "Workflow case"})
        assert created.status_code == 201
        case_id = created.json()["id"]
        assert client.patch(
            f"/api/v2/cases/{case_id}/status", json={"status": "closed"}
        ).status_code == 422
        assert client.patch(
            f"/api/v2/cases/{case_id}/status", json={"status": "in_review"}
        ).status_code == 200
        assert client.patch(
            f"/api/v2/cases/{case_id}/status", json={"status": "closed"}
        ).status_code == 200
        assert client.patch(
            f"/api/v2/cases/{case_id}/status", json={"status": "open"}
        ).status_code == 422
        assert client.patch(
            f"/api/v2/cases/{case_id}/status",
            json={"status": "open", "reason": "Additional evidence arrived"},
        ).status_code == 200

        payload = json.dumps([
            {"timestamp": "2026-03-01T10:00:00Z", "actor": "alice", "host": "host-a", "action": "login"},
            {"timestamp": "2026-03-01T10:01:00Z", "actor": "bob", "host": "host-b", "action": "login"},
        ])
        imported = client.post(
            f"/api/v2/cases/{case_id}/evidence",
            data={"parser": "json"},
            files={"file": ("events.json", payload, "application/json")},
        )
        evidence_id = imported.json()["evidence_id"]
        evidence = client.get(f"/api/v2/cases/{case_id}/evidence").json()["evidence"]
        assert evidence[0]["id"] == evidence_id
        assert client.get(f"/api/v2/evidence/{evidence_id}").status_code == 200

        first = client.get(f"/api/v2/cases/{case_id}/timeline?limit=1")
        assert first.status_code == 200
        assert len(first.json()["events"]) == 1
        second = client.get(
            f"/api/v2/cases/{case_id}/timeline?limit=1&cursor={first.json()['next_cursor']}"
        )
        assert second.status_code == 200
        assert first.json()["events"][0]["id"] != second.json()["events"][0]["id"]
        assert client.get(f"/api/v2/cases/{case_id}/timeline?actor=alice").json()["events"][0]["actor"] == "alice"

        note = client.post(f"/api/v2/cases/{case_id}/notes", json={"text": "<script>note</script>"})
        assert note.status_code == 201
        assert client.get(f"/api/v2/cases/{case_id}/notes").json()["notes"][0]["text"].startswith("<script>")
        assert client.post(f"/api/v2/cases/{case_id}/tags", json={"name": "priority"}).status_code == 201
        assert client.post(
            f"/api/v2/cases/{case_id}/bookmarks",
            json={"event_id": first.json()["events"][0]["id"]},
        ).status_code == 201

        assert client.delete(f"/api/v2/evidence/{evidence_id}").status_code == 200
        assert client.get(f"/api/v2/evidence/{evidence_id}").status_code == 404
        assert client.get(f"/api/v2/cases/{case_id}/timeline").json()["events"] == []


def test_v2_cross_tenant_case_access_is_not_disclosed(monkeypatch):
    with TestClient(app) as client:
        case = client.post("/api/v2/cases", json={"title": "Tenant one"}).json()["id"]
        monkeypatch.setattr(settings, "authentication_backend", "local_bearer")
        monkeypatch.setattr(settings, "auth_tokens", "tenant-two:token")
        response = client.get(f"/api/v2/cases/{case}", headers={"Authorization": "Bearer token"})
        assert response.status_code == 404
        monkeypatch.setattr(settings, "authentication_backend", "none")
