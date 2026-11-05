# Digital Forensics Investigation Extension v2 Status

Baseline command: `python -m pytest -q`  
Baseline result: **123 passed, 1 warning**  
Status rule: a feature is only **Implemented** when a passing test proves it.

| Work package | Status | Evidence | Test |
|---|---|---|---|
| W1 OIDC/JWT authentication and roles | Partial | Local bearer ownership exists in `app/main.py` and `app/forensics/legacy.py`; OIDC/JWKS and role administration are absent | `tests/test_api.py` |
| W2 Complete data model and Alembic migrations | Missing | v2 event/finding tables exist in `app/forensics/persistence.py`; full tenant model and Alembic directory are absent | `tests/test_v2_forensics.py` |
| W3 Windows XML, EVTX, Firefox parsers | Missing | Current parsers cover JSON/CSV/Linux/web in `app/forensics/parsers.py` | `tests/test_v2_forensics.py` |
| W4 Evidence/workflow management | Partial | Basic case/evidence/timeline/ownership exists in `app/forensics/legacy.py`; notes, tags, bookmarks, incidents, deletion, and transitions are absent | `tests/test_api.py` |
| W5 Sequence and incident engine | Missing | Current rules are independent deterministic rules in `app/forensics/rules.py`; sequence data and incident grouping are absent | `tests/test_v2_forensics.py` |
| W6 HMAC custody, verification, RFC 3161 anchoring | Partial | Local hash custody and local-file anchoring exist in `app/forensics/legacy.py`; HMAC, CLI verification, and TSA support are absent | `tests/test_api.py` |
| W7 Scanning, quotas, deletion, rate limiting | Partial | Analysis rate limiting exists in `app/main.py`; ClamAV, quotas, archive rejection, and secure deletion are absent | `tests/test_api.py` |
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

The challenge vertical remains **media provenance and evidence** from the
existing README. The supplied track is **AI-Powered Digital Forensics
Investigation Platform**.
