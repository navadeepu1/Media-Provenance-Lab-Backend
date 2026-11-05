# Digital Forensics Investigation Extension v2 Status

Baseline command: `python -m pytest -q`  
Baseline result: **128 passed, 1 warning**
Status rule: a feature is only **Implemented** when a passing test proves it.

| Work package | Status | Evidence | Test |
|---|---|---|---|
| W1 OIDC/JWT authentication and roles | Partial | Local bearer ownership exists in `app/main.py` and `app/forensics/legacy.py`; OIDC/JWKS and role administration are absent | `tests/test_api.py` |
| W2 Complete data model and Alembic migrations | Partial | Full v2 model declarations and an Alembic initial migration exist in `app/forensics/persistence.py` and `alembic/versions/0001_v2_investigation_schema.py`; downgrade coverage is still absent | `tests/test_v2_forensics.py` |
| W3 Windows XML, EVTX, Firefox parsers | Partial | Windows XML and Firefox parsers are implemented in `app/forensics/parsers.py`; EVTX and four-test parser coverage are absent | `tests/test_v2_forensics.py` |
| W4 Evidence/workflow management | Implemented locally | Tenant-scoped case CRUD, `open -> in_review -> closed` transitions with reason-gated reopen, evidence list/detail/soft-delete/admin hard-delete, notes, controlled tags, bookmarks, finding status updates, filtered cursor timelines, and audit entries exist in `app/main.py` and `app/forensics/persistence.py`; production RBAC remains deployment-specific | `tests/test_v2_forensics.py` |
| W5 Sequence and incident engine | Implemented | Deterministic sequence definitions, sequence findings, and 30-minute incident grouping exist in `app/forensics/sequences.json` and `app/forensics/incidents.py` | `tests/test_v2_forensics.py` |
| W6 HMAC custody, verification, RFC 3161 anchoring | Partial | HMAC custody append/verification exists in `app/forensics/custody.py`; CLI verification and RFC 3161 TSA support are absent | `tests/test_v2_forensics.py` |
| W7 Scanning, quotas, deletion, rate limiting | Partial | Analysis rate limiting and local secure deletion exist in `app/main.py` and `app/storage.py`; ClamAV, quotas, and archive rejection remain absent | `tests/test_api.py`, `tests/test_v2_forensics.py` |
| W8 AI citation validator and adapters | Missing | Existing assistant is deterministic keyword retrieval; citation validation and provider adapters are absent | `tests/test_api.py` |
| W9 PostgreSQL, S3, RQ, backup/restore | Partial | Configuration boundaries exist in `app/storage.py` and `app/queue.py`; migrations, S3 implementation, worker entrypoint, and backup scripts are absent | Existing API tests |
| W10 Investigation UI and report export | Partial | Existing local case/timeline controls are in `app/static/index.html` and `app/static/app.js`; v2 tabs and complete report export are absent | `tests/test_accessibility.py` |
| W11 Synthetic forensic evaluation | Missing | Existing media evaluation scripts do not generate forensic log scenarios or rule metrics | No passing v2 test |
| W12 Advanced media/audio/C2PA/detector governance | Partial | Existing media/C2PA/video/detector capabilities are documented; full-frame/audio/drift/governance requirements are absent | Existing media/detector tests |

## Current v2 slice

Implemented and tested:

- strict normalized events and fixed action vocabulary;
- JSON, CSV, Linux auth, and web access parsers;
- parser warnings for malformed Linux lines;
- tenant-scoped v2 event/finding persistence;
- deterministic login-burst, off-hours, privilege, access-burst, and
  delete-burst rules;
- `/api/v2` health, evidence ingestion, timeline, and findings routes.
- workflow CRUD for cases, evidence, notes, tags, bookmarks, finding review
  status, and audit-backed lifecycle changes.

The challenge vertical remains **media provenance and evidence** from the
existing README. The supplied track is **AI-Powered Digital Forensics
Investigation Platform**.
