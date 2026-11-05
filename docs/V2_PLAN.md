# Investigation Platform v2 Plan

## Audit baseline

- Challenge vertical: **media provenance and evidence** (the vertical named in
  the existing README).
- Track: **AI-Powered Digital Forensics Investigation Platform** (the track
  supplied in the project brief).
- Existing production-architecture, limitations, and remaining-development
  documents were present and reviewed.
- Baseline command: `python -m pytest -q`
- Baseline result: **121 passed, 1 warning**.
- Existing `/api/v1` routes and tests are a compatibility boundary. v2 work
  must not change their response contracts.

## Milestones

| Milestone | Scope | Exit test |
|---|---|---|
| A0 | Audit, this plan, assumptions, and v2 package boundary | `tests/test_v2_plan.py` |
| A1 | Tenant/user/case/evidence/event/finding persistence, migrations, repositories | `tests/test_v2_persistence.py` |
| A2 | Development bearer authentication, OIDC boundary, roles, tenant isolation | `tests/test_v2_auth.py` |
| A3 | Strict event schema and generic/Linux/web parsers | `tests/test_v2_parsers.py` |
| A4 | Windows XML/EVTX, browser copies, filesystem metadata adapters | `tests/test_v2_parsers.py` |
| A5 | Upload limits, hashing, scan status, custody, list/detail/soft delete | `tests/test_v2_evidence.py` |
| A6 | Deterministic login, privilege, access, and delete rules | `tests/test_v2_rules.py` |
| A7 | Sequences, causal links, incidents, deterministic timeline filters | `tests/test_v2_incidents.py` |
| A8 | Notes, tags, bookmarks, finding status, case transitions | `tests/test_v2_workflow.py` |
| A9 | Custody verification CLI/API and HTML/JSON report export | `tests/test_v2_custody.py` |
| A10 | Synthetic planted-incident generator and evaluation metrics | `tests/test_v2_evaluation.py` |
| A11 | Investigation UI and accessibility checks | `tests/test_v2_ui.py` |
| A12 | ClamAV, quotas, Redis limits, secure deletion, audit hardening | `tests/test_v2_security.py` |
| B1 | Optional citation-validated AI summaries | `tests/test_v2_ai.py` |
| B2 | PostgreSQL, Alembic, backup/restore validation | `tests/test_v2_postgres.py` |
| B3 | Redis/RQ worker deployment boundary | `tests/test_v2_queue.py` |
| B4 | Swimlane, heatmap, and accessibility verification | `tests/test_v2_ui.py` |
| B5 | Geolocation/new-host/log-gap rules and RFC 3161 anchoring | `tests/test_v2_phase_b.py` |
| B6 | ClamAV integration | `tests/test_v2_security.py` |
| C1-C5 | Full video, audio presence, C2PA verification, drift, detector governance | `tests/test_v2_advanced.py` |

## Requirement map

| Requirement | Module(s) | Milestone | Test file |
|---|---|---|---|
| P0-1 Suspicious correlation | `app/forensics/rules/`, `app/forensics/scoring.py` | A6 | `tests/test_v2_rules.py` |
| P0-2 Incidents/sequences/grouping | `app/forensics/incidents.py`, `app/forensics/sequences.py` | A7 | `tests/test_v2_incidents.py` |
| P0-3 Evidence formats | `app/forensics/parsers/` | A3-A4 | `tests/test_v2_parsers.py` |
| P0-4 Workflow and filters | `app/forensics/repositories/`, `app/main.py` | A5-A8 | `tests/test_v2_workflow.py` |
| P0-5 AI summaries | `app/forensics/ai.py` | B1 | `tests/test_v2_ai.py` |
| P1-6 OIDC/roles/tenants | `app/forensics/auth.py`, repositories | A1-A2 | `tests/test_v2_auth.py` |
| P1-7 Production services | `alembic/`, `app/forensics/storage.py`, queue boundary | A1/B2/B3 | `tests/test_v2_postgres.py` |
| P1-8 Custody | `app/forensics/custody.py`, `scripts/verify_custody.py` | A5/A9/B5 | `tests/test_v2_custody.py` |
| P1-9 Security hardening | upload service, scan service, rate limiter | A5/A12/B6 | `tests/test_v2_security.py` |
| P2-10 Advanced media | existing media pipeline plus v2 capability adapters | C1-C5 | `tests/test_v2_advanced.py` |
| P2-11 Evaluation | `scripts/make_log_dataset.py`, `scripts/evaluate_forensics.py` | A10 | `tests/test_v2_evaluation.py` |
| P2-12 UI/export | `app/static/investigation/`, report exporter | A11/B4 | `tests/test_v2_ui.py` |

## Constraints

- Rules, severities, statuses, and findings are deterministic; AI can only
  summarize existing findings.
- Every finding must contain at least one event ID or be rejected.
- Raw source text is retained separately from normalized event fields.
- All v2 tables and repository queries are tenant-scoped.
- Timestamps are stored in UTC while preserving the original offset and
  timezone-assumed status.
- Parsers return warnings instead of raising on malformed input.
- External services remain optional and disabled by default.
