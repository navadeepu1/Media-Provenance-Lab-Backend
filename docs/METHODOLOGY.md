# Methodology

The fusion rules are deterministic:

- R1 `STRONG_SIGNALS`: at least two different families are strong.
- R2 `WEAK_SIGNALS`: no R1, with at least one weak or strong family.
- R3 `INCONCLUSIVE`: fewer than two determined families or a failed quality gate.
- R4 `NO_SIGNALS`: at least two determined families and all are none.

The current image modules are ELA, noise residual, ORB copy-move, and an explicit not-determined learned-detector placeholder. Scores are bounded between zero and one. No score alone is a verdict.

Provenance is context rather than a verdict: camera fields, software, capture time, and a boolean location-presence flag are exposed without GPS coordinates. JPEG quantization is used as a quality estimate. If an embedded JPEG thumbnail is present, its pHash distance from a resized main image is reported as context; the current fusion rules do not penalize this signal until a validation split demonstrates that it improves results. A small image with no camera fields and a low estimated JPEG quality is labelled as a likely messaging-style re-encoded copy.
