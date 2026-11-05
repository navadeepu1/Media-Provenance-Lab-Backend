import hashlib
import json

import pytest

from scripts.check_model_governance import verify


def test_governance_verification_requires_matching_provenance(tmp_path):
    model = tmp_path / "model.onnx"
    model.write_bytes(b"model")
    record = tmp_path / "record.json"
    record.write_text(json.dumps({
        "artifact_sha256": hashlib.sha256(b"model").hexdigest(),
        "upstream_url": "https://example.org/model",
        "revision": "abc123",
        "author": "Example",
        "model_license": "MIT",
        "dataset_license": "CC-BY",
        "redistribution_permission": True,
    }))
    assert verify(model, record)["status"] == "verified"


def test_governance_rejects_unverified_distribution(tmp_path):
    model = tmp_path / "model.onnx"
    model.write_bytes(b"model")
    record = tmp_path / "record.json"
    record.write_text(json.dumps({"redistribution_permission": False}))
    with pytest.raises(ValueError, match="missing"):
        verify(model, record)
