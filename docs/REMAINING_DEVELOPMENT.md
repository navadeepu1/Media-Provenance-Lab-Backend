# Remaining development requirements

The local foundation, SQLite job/report persistence, chunked upload handling, security headers, provenance context, embedded-thumbnail inspection, and the JPEG quality gate are implemented. The following work is still required before the challenge definition of done can be claimed:

1. **Exact challenge metadata and repository submission**: obtain the official vertical, track, branch, and judging document; replace the README assumption; push `main` to the public GitHub repository.
2. **Ingest hardening**: header inspection and expanded corrupt-image/codec regression fixtures are implemented; add platform-specific codec coverage before release.
3. **Provenance**: optional C2PA capability/manifest status is implemented and tested; upstream C2PA wheel availability still depends on the deployment platform.
4. **Forensics**: tiled ELA/noise, connected-region checks, offset clustering, spatial copy-move validation, and synthetic fixture tests are implemented; thresholds still require evaluation-set calibration.
5. **Detector**: lazy loading, checksum verification, timeout, missing-weight behavior, and a reproducible Platt calibration tool are implemented. The bundled artifact's license and upstream revision remain unverified, so public model selection is still blocked.
6. **Known items**: deterministic synthetic seed records, pHash/dHash threshold matching, recompression tests, and UI context cards are implemented; production references still require reviewed, licensed records.
7. **Video**: sample one frame per second up to 30 frames, aggregate frame tiers at the 10% boundary, retain strongest-frame thumbnails, and display frame-level context in the UI.
8. **Explainer**: Gemini/Groq adapters, an 8-second timeout, strict output validation, deterministic template fallback, and SQLite-backed explanation cache are implemented. Provider keys belong only in private Render environment variables.
9. **API/security**: CORS allowlisting, request IDs, security headers, and bounded analysis rate limiting are implemented; strict expiration semantics, scheduled cleanup, and the complete admin test matrix remain.
10. **Demo/evaluation**: eight fixed-seed synthetic samples, a CC0-1.0 evaluation manifest and split, and `eval/results.json` are implemented; real-world licensed evaluation data is still required for accuracy claims.
11. **UI/accessibility**: known-item sections, video frames, focus-visible keyboard styling, responsive report overflow handling, and 360px regression tests are implemented; browser-level assistive-technology testing remains recommended.
12. **Deployment**: create the Render service, configure only approved secrets, measure cold start/memory/latency, run the live smoke test, and record observed values.
13. **Release**: full test and coverage run, offline test, size/secret scans, documentation review, tag `v1.0`, and push.

External requirements are the official challenge document, a GitHub repository with push access, a Render account, the optional provider/model credentials if those features are enabled, and licensed evaluation sources. No secret or paid service is required for the offline baseline.
