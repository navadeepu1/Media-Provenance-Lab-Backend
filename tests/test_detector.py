import time

import numpy as np
import onnx
import pytest
from onnx import TensorProto, helper, numpy_helper
from PIL import Image

from app import detector as det

def test_successful_inference_with_checksum(tiny_model, image):
    import hashlib
    import math

    expected_hash = hashlib.sha256(tiny_model.read_bytes()).hexdigest()
    out = det.OnnxDetector(tiny_model, expected_sha256=expected_hash).predict(image)
    assert out.status == "ok"
    # softmax([3, -3])[0] = 1 / (1 + e^-6)
    assert out.ai_probability == pytest.approx(1 / (1 + math.exp(-6)), abs=1e-5)

def build_tiny_model(path, bias=(3.0, -3.0)):
    """Tiny ONNX model with the real I/O shape: [1,3,224,224] -> logits [1,2].
    Its output is always `bias`, so expected results are exact."""
    x = helper.make_tensor_value_info("input", TensorProto.FLOAT, [1, 3, 224, 224])
    y = helper.make_tensor_value_info("logits", TensorProto.FLOAT, [1, 2])
    pool = helper.make_node("ReduceMean", ["input"], ["pooled"], axes=[2, 3], keepdims=0)
    weight = numpy_helper.from_array(np.zeros((3, 2), dtype=np.float32), name="weight")
    matmul = helper.make_node("MatMul", ["pooled", "weight"], ["projected"])
    bias_t = numpy_helper.from_array(np.array(bias, dtype=np.float32), name="bias")
    add = helper.make_node("Add", ["projected", "bias"], ["logits"])
    graph = helper.make_graph([pool, matmul, add], "tiny", [x], [y], initializer=[weight, bias_t])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = 8
    onnx.checker.check_model(model)
    onnx.save(model, str(path))
    return path


@pytest.fixture
def tiny_model(tmp_path):
    return build_tiny_model(tmp_path / "tiny.onnx")


@pytest.fixture
def image():
    return Image.new("RGB", (640, 480), (120, 80, 40))


# --- preprocessing ---------------------------------------------------------

def test_rgb_conversion_accepts_grayscale_and_rgba():
    for mode in ("L", "RGBA"):
        x = det.preprocess(Image.new(mode, (50, 40)))
        assert x.shape == (1, 3, 224, 224)


def test_resizes_non_square_input_to_224():
    assert det.preprocess(Image.new("RGB", (1000, 300))).shape == (1, 3, 224, 224)


def test_normalization_values_white_and_black():
    white = det.preprocess(Image.new("RGB", (8, 8), (255, 255, 255)))
    black = det.preprocess(Image.new("RGB", (8, 8), (0, 0, 0)))
    assert np.allclose(white[0, :, 0, 0], (1 - det.MEAN) / det.STD, atol=1e-4)
    assert np.allclose(black[0, :, 0, 0], (0 - det.MEAN) / det.STD, atol=1e-4)


def test_nchw_channel_order_is_red_first():
    x = det.preprocess(Image.new("RGB", (8, 8), (255, 0, 0)))
    assert np.allclose(x[0, 0], (1 - 0.485) / 0.229, atol=1e-4)  # red channel
    assert np.allclose(x[0, 1], (0 - 0.456) / 0.224, atol=1e-4)  # green channel
    assert x.dtype == np.float32


# --- output mapping and softmax -------------------------------------------

def test_softmax_sums_to_one_and_is_stable():
    p = det.softmax(np.array([1.0, 2.0, 3.0]))
    assert pytest.approx(p.sum()) == 1.0
    assert np.all(np.isfinite(det.softmax(np.array([1000.0, 1000.0]))))


def test_index_zero_maps_to_artificial():
    assert det.interpret_logits([3.0, -3.0]).ai_probability > 0.99
    assert det.interpret_logits([-3.0, 3.0]).ai_probability < 0.01


def test_unexpected_output_shape_is_not_determined():
    out = det.interpret_logits([1.0, 2.0, 3.0])
    assert out.status == "not_determined"


# --- failure handling ------------------------------------------------------

def test_missing_model_is_not_determined(tmp_path, image):
    out = det.OnnxDetector(tmp_path / "missing.onnx").predict(image)
    assert out.status == "not_determined"
    assert "missing" in out.reason


def test_checksum_mismatch_is_not_determined(tiny_model, image):
    out = det.OnnxDetector(tiny_model, expected_sha256="0" * 64).predict(image)
    assert out.status == "not_determined"
    assert "checksum" in out.reason


def test_invalid_onnx_file_is_not_determined(tmp_path, image):
    bad = tmp_path / "bad.onnx"
    bad.write_bytes(b"this is not a model")
    out = det.OnnxDetector(bad).predict(image)
    assert out.status == "not_determined"
    assert "not a valid ONNX" in out.reason


def test_runtime_failure_is_not_determined(tiny_model, image, monkeypatch):
    def boom(session, tensor):
        raise RuntimeError("boom")

    monkeypatch.setattr(det.OnnxDetector, "_run", staticmethod(boom))
    out = det.OnnxDetector(tiny_model).predict(image)
    assert out.status == "not_determined"
    assert "inference failed" in out.reason


def test_timeout_is_not_determined(tiny_model, image, monkeypatch):
    def slow(session, tensor):
        time.sleep(0.5)
        return np.zeros((1, 2))

    monkeypatch.setattr(det.OnnxDetector, "_run", staticmethod(slow))
    out = det.OnnxDetector(tiny_model, timeout=0.05).predict(image)
    assert out.status == "not_determined"
    assert "timed out" in out.reason


def test_loading_is_lazy(tiny_model):
    d = det.OnnxDetector(tiny_model)
    assert d.status == "not_loaded"


# --- successful inference --------------------------------------------------


# --- signal mapping --------------------------------------------------------

@pytest.mark.parametrize(
    "p, strength",
    [(0.95, "strong"), (0.70, "weak"), (0.10, "none")],
)
def test_signal_strength_follows_thresholds(p, strength):
    sig = det.learned_signal(det.DetectorOutput("ok", ai_probability=p))
    assert sig["strength"] == strength
    assert sig["family"] == "learned"


def test_failed_detector_never_becomes_none_or_human():
    sig = det.learned_signal(det.DetectorOutput("not_determined", reason="x"))
    assert sig["strength"] == "not_determined"
    assert sig["score"] is None


