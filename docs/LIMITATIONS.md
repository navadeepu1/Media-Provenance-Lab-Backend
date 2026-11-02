# Limitations

This build does not identify people, fetch URLs, inspect audio, or call paid
services. Free-host storage is ephemeral and SQLite data is lost after a
restart or redeploy.

The local ONNX detector is implemented with lazy loading, checksum
verification, timeout handling, and explicit `not_determined` failures, but
it remains a single uncalibrated model and is excluded from fusion tiers.
Weights and their redistribution license must be verified before public use.

C2PA capability and manifest inspection are implemented as an optional
integration. When the `c2pa-python` binding is unavailable, the report says
that C2PA was not checked; absence of a manifest is never inferred from that
state.

Video analysis is implemented but limited to one sampled frame per second,
up to 30 seconds/frames. Audio is not analyzed, and edits between sampled
frames may be missed.

Images remain subject to hard byte, pixel, and longest-side limits before
decoding. Accepted images larger than `ANALYSIS_MAX_SIDE` are safely reduced
only for in-memory forensic analysis; the original dimensions and the working
dimensions are reported. This bounds CPU and memory use without silently
accepting unlimited uploads.
