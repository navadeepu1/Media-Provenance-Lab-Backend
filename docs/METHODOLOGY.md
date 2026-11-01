# Methodology

The fusion rules are deterministic:

- R1 `STRONG_SIGNALS`: at least two different families are strong.
- R2 `WEAK_SIGNALS`: no R1, with at least one weak or strong family.
- R3 `INCONCLUSIVE`: fewer than two determined families or a failed quality gate.
- R4 `NO_SIGNALS`: at least two determined families and all are none.

The current image modules are tiled ELA, tiled noise residual, ORB copy-move with spatial region validation, and a local ONNX learned detector. The detector resizes RGB input to 224x224, applies the ImageNet mean and standard deviation, and maps output index 0 to artificial and index 1 to human. Scores are bounded between zero and one. No score alone is a verdict.

The learned detector is loaded lazily from `DETECTOR_LOCAL_PATH` and its SHA-256 is verified before loading when configured. Missing, invalid, mismatched, timed-out, or failed inference returns `not_determined`. The detector is currently excluded from fusion tier decisions until calibration on a validation split is complete.

Provenance is context rather than a verdict: camera fields, software, capture time, and a boolean location-presence flag are exposed without GPS coordinates. JPEG quantization is used as a quality estimate. C2PA capability and manifest status are reported separately; unavailable C2PA support is not treated as absence of provenance. If an embedded JPEG thumbnail is present, its pHash distance from a resized main image is reported as context; the current fusion rules do not penalize this signal until a validation split demonstrates that it improves results. A small image with no camera fields and a low estimated JPEG quality is labelled as a likely messaging-style re-encoded copy.
