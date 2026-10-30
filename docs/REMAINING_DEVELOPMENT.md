# Remaining development requirements

The local foundation and SQLite job/report persistence are implemented. The following work is still required before the challenge definition of done can be claimed:

1. **Exact challenge metadata and repository submission**: obtain the official vertical, track, branch, and judging document; replace the README assumption; push `main` to the public GitHub repository.
2. **Ingest hardening**: stream multipart uploads in chunks, validate WebP and MP4 signatures separately, inspect headers before pixel decode, probe MP4 duration with OpenCV, and add 413/415/422 regression tests.
3. **Provenance**: implement piexif thumbnail extraction/comparison, JPEG quantization quality estimates, messaging-copy context, and a tested C2PA capability check.
4. **Forensics**: implement tiled ELA/noise processing, contiguous-region validation, copy-move offset clustering, and generated fixture tests.
5. **Detector**: select a permissively licensed small ONNX model, record licence/revision/SHA-256, add lazy loading, calibration, timeout, and missing-weight behavior.
6. **Known items**: add database seed records, pHash/dHash threshold matching, reproducible synthetic seed generation, and UI context cards.
7. **Video**: sample one frame per second up to 30 frames, aggregate frame tiers at the 10% boundary, and return strongest-frame thumbnails.
8. **Explainer**: add provider adapters, JSON-only prompt construction, strict output validation, timeout fallback, and SQLite-backed explanation cache.
9. **API/security**: add CORS allowlisting, request IDs, security headers, IP rate limiting, strict expiration semantics, scheduled cleanup, and a complete admin test matrix.
10. **Demo/evaluation**: generate eight fixed-seed samples, build the licensed evaluation manifest and split, produce `eval/results.json`, and ensure README numbers are read from that file.
11. **UI/accessibility**: render provenance and known-item sections, video frames, interrupted/expired states, and test keyboard/focus behavior at 360px.
12. **Deployment**: create the Render service, configure only approved secrets, measure cold start/memory/latency, run the live smoke test, and record observed values.
13. **Release**: full test and coverage run, offline test, size/secret scans, documentation review, tag `v1.0`, and push.

External requirements are the official challenge document, a GitHub repository with push access, a Render account, the optional provider/model credentials if those features are enabled, and licensed evaluation sources. No secret or paid service is required for the offline baseline.
