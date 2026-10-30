# Remaining development requirements

The local foundation, SQLite job/report persistence, chunked upload handling, security headers, provenance context, embedded-thumbnail inspection, and the JPEG quality gate are implemented. The following work is still required before the challenge definition of done can be claimed:

1. **Exact challenge metadata and repository submission**: obtain the official vertical, track, branch, and judging document; replace the README assumption; push `main` to the public GitHub repository.
2. **Ingest hardening**: inspect headers before pixel decode and add the remaining 413/415/422 regression tests for decode bombs, corrupt media, and codec edge cases.
3. **Provenance**: add a tested C2PA capability check and expand embedded-thumbnail fixtures; EXIF redaction, quantization estimates, messaging-copy context, and thumbnail comparison are present.
4. **Forensics**: implement tiled ELA/noise processing, contiguous-region validation, copy-move offset clustering, and generated fixture tests.
5. **Detector**: select a permissively licensed small ONNX model, record licence/revision/SHA-256, add lazy loading, calibration, timeout, and missing-weight behavior.
6. **Known items**: add database seed records, pHash/dHash threshold matching, reproducible synthetic seed generation, and UI context cards.
7. **Video**: sample one frame per second up to 30 frames, aggregate frame tiers at the 10% boundary, and return strongest-frame thumbnails.
8. **Explainer**: template fallback and strict JSON-output validation are present; add Gemini/Groq provider adapters, an 8-second timeout, and SQLite-backed explanation cache. Provider keys belong only in private Render environment variables.
9. **API/security**: add CORS allowlisting, request IDs, security headers, IP rate limiting, strict expiration semantics, scheduled cleanup, and a complete admin test matrix.
10. **Demo/evaluation**: generate eight fixed-seed samples, build the licensed evaluation manifest and split, produce `eval/results.json`, and ensure README numbers are read from that file.
11. **UI/accessibility**: render provenance and known-item sections, video frames, interrupted/expired states, and test keyboard/focus behavior at 360px.
12. **Deployment**: create the Render service, configure only approved secrets, measure cold start/memory/latency, run the live smoke test, and record observed values.
13. **Release**: full test and coverage run, offline test, size/secret scans, documentation review, tag `v1.0`, and push.

External requirements are the official challenge document, a GitHub repository with push access, a Render account, the optional provider/model credentials if those features are enabled, and licensed evaluation sources. No secret or paid service is required for the offline baseline.
