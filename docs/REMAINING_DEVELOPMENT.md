# Remaining development requirements

The offline baseline is implemented and automated tests pass. The remaining
items below are release gates, not missing core pipeline functionality. See
[RELEASE_CHECKLIST.md](./RELEASE_CHECKLIST.md) for the evidence required to
close each gate.

The local foundation, SQLite job/report persistence, durable job deadlines and cancellation, structured JSON event logging, timing metrics, chunked upload handling, security headers, provenance context, embedded-thumbnail inspection, and the JPEG quality gate are implemented. The following work is still required before the challenge definition of done can be claimed:

1. **PARTIAL/BLOCKED: challenge submission**: the supplied brief confirms a
   public repository, less than 10 MB, exactly one branch, at most two
   attempts, a README, and evaluation across code quality, security,
   efficiency, testing, accessibility, and problem alignment. The deadline is
   November 6, 2026. Push the reviewed `main` branch; no submission URL was
   requested.
2. **Ingest hardening**: header inspection and corrupt-image/codec regression fixtures are implemented; add platform-specific codec coverage before release.
3. **Provenance**: optional C2PA capability/manifest status is implemented and tested; upstream C2PA wheel availability still depends on the deployment platform.
4. **Forensics**: tiled ELA/noise, connected-region checks, offset clustering, spatial copy-move validation, and synthetic fixture tests are implemented; thresholds still require evaluation-set calibration.
5. **PARTIAL/BLOCKED: detector**: lazy loading, checksum verification, timeout, missing-weight behavior, and a reproducible Platt calibration tool are implemented. The detector is optional for this offline prototype; do not commit or enable the unverified model artifact until its upstream license and revision are documented.
6. **Known items**: deterministic synthetic seed records, pHash/dHash threshold matching, recompression tests, and UI context cards are implemented; production references still require reviewed, licensed records.
7. **Video**: sample one frame per second up to 30 frames, aggregate frame tiers at the 10% boundary, retain strongest-frame thumbnails, and display frame-level context in the UI.
8. **Explainer**: Gemini/Groq adapters, an 8-second timeout, strict output validation, deterministic template fallback, and SQLite-backed explanation cache are implemented. Provider keys belong only in private Render environment variables.
9. **API/security**: CORS allowlisting, request IDs, security headers, and bounded analysis rate limiting are implemented; strict expiration semantics, scheduled cleanup, and the complete admin test matrix remain.
10. **Demo/evaluation**: eight fixed-seed synthetic samples, a CC0-1.0 evaluation manifest and split, and `eval/results.json` are implemented. The manifest-driven real-data evaluator and licensing/consent fields are implemented; independently verified multi-source data is still required for accuracy claims.
11. **PARTIAL: UI/accessibility**: known-item sections, video frames, focus-visible keyboard styling, responsive report overflow handling, duplicate-submit protection, explicit network/API error announcements, cancellation controls, uncertainty presentation, 360px regression tests, and an integrated-browser workflow record are implemented; native screen-reader testing remains required.
12. **OUT OF SCOPE: hosted deployment**: Render deployment and production cold-start measurements are not required for this prototype.
13. **PENDING release gate**: full test and coverage run, offline test, size/secret scans, documentation review, tag `v1.0`, and push.
14. **P2 production architecture**: service configuration boundaries, readiness checks, local review/deletion/audit primitives, explicit storage/queue status, and optional local bearer ownership are implemented. PostgreSQL migrations, a separately deployed RQ worker, S3-compatible storage, OIDC, and distributed rate limiting still require deployment-specific implementation.
15. **P3 advanced capabilities**: capability reporting, local human-review tasks, timing metrics, deterministic suspicious-activity findings, browser-history/application adapters, custody anchoring, and current C2PA status are implemented. Full/adaptive video, audio synchronization, secure URL ingestion, C2PA signing/chain visualization, OIDC review assignment, and drift monitoring/alerting remain incomplete.

External requirements are a public GitHub repository with push access. A
licensed evaluation set is needed only for real-world accuracy claims, model
provenance is needed only if the optional detector is distributed/enabled, and
no Render account, secret, or paid service is required for the offline
prototype.
