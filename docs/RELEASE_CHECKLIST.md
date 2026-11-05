# Release checklist

The application code and automated tests are release-ready for the offline
baseline. The following gates require external evidence and must be completed
before a public challenge submission.

## External gates

- [x] **Challenge metadata**: the supplied brief requires a public repository
  under 10 MB, exactly one branch, a README, and no more than two attempts.
  Evaluation focuses on code quality, security, efficiency, testing,
  accessibility, and problem-statement alignment. The deadline is November 6,
  2026. A vertical/track should still be named in the final README if the
  challenge requires one.
- [x] **Prototype deployment scope**: Render deployment and production
  measurements are explicitly out of scope for this prototype.
- [ ] **Detector provenance (only if distributed/enabled)**: record upstream
  repository, immutable revision, author, license, download URL, checksum, and
  redistribution permission in `docs/MODEL_CARD.md`. Do not commit or enable
  the unverified `model_int8.onnx` artifact.
- [ ] **Licensed evaluation set (only for accuracy claims)**: provide source
  URLs, licenses, attribution, consent records, labels, and source-group splits
  in `eval_data/manifest.json`. Existing personal images and derived examples
  are sufficient for demonstrating the workflow, but not for general
  real-world accuracy claims.
- [ ] **Assistive-technology test (polish, not prototype blocking)**: manually test keyboard-only operation,
  focus order, screen-reader names/status updates, error announcements, image
  alternatives, and 360px layout in a real browser with an available
  assistive technology. Record browser, OS, tool, date, and result.
- [ ] **Production services**: configure PostgreSQL, Redis/RQ, private object
  storage, authentication, distributed rate limiting, backups, and deletion
  verification. Local mode is not production-ready.
- [ ] **Privacy operations**: publish the privacy and retention policy, verify
  report deletion removes source/artifact data, and restrict audit logs to
  authorized operators.

## Local release commands

```powershell
python -m pytest --cov=app --cov-report=term-missing
python scripts/generate_eval.py
python scripts/evaluate_dataset.py
python scripts/calibrate_forensics.py
python scripts/check_secrets.py
python scripts/check_repo_size.py
```

`evaluate_dataset.py` and `calibrate_forensics.py` require a reviewed real-data
manifest. Their metrics are not production accuracy claims. Keep all variants
from one original source in the same split.

## Release evidence

- [ ] Tests and coverage output attached to the release record.
- [ ] Secret and repository-size scans passed.
- [ ] Offline sample, report, heatmap, and HTML export manually opened.
- [ ] Methodology, limitations, model card, data sources, and deployment docs
  reviewed against the deployed commit.
- [ ] `v1.0` tag points to the reviewed commit.
- [ ] Public repository contains no personal images, private consent details,
  credentials, or unverified third-party assets.
