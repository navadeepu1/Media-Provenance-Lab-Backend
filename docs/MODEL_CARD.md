# Detector model card

The repository currently contains `model_int8.onnx`, an ONNX Runtime quantized
artifact with SHA-256
`c58229f69570be40698120b31defd985c63904575baacffad1a7866fda6efcc5`.
Its graph exposes `pixel_values` and `logits` and uses opset 18.

The artifact's upstream author, revision, and license are not embedded in the
ONNX metadata and no license evidence is present in this repository. Therefore
the application verifies the checksum but does **not** claim that the artifact
is permissively licensed or suitable for redistribution. A release must replace
or document this artifact with a verifiable upstream license and revision before
public deployment.

Calibration is implemented by `scripts/calibrate_detector.py` and requires a
licensed held-out CSV with `score,label` columns. No calibration file is enabled
by default, and the detector remains excluded from fusion tiers until measured
validation results are recorded.
