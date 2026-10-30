"""Local ONNX AI-image detector.

Returns the model's probability that an image is AI-generated. Any failure
returns "not_determined". A failure is never reported as human or clean.
"""

from __future__ import annotations
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

from .config import settings
from .constants import (
    DETECTOR_ARTIFICIAL_INDEX,
    DETECTOR_INPUT_SIZE,
    DETECTOR_MEAN,
    DETECTOR_STD,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

MEAN = np.array(DETECTOR_MEAN, dtype=np.float32)
STD = np.array(DETECTOR_STD, dtype=np.float32)
INFERENCE_TIMEOUT_SECONDS = 15.0

# PROVISIONAL thresholds on the AI probability. Replace them with values chosen
# on the validation split, and record the choice in docs/METHODOLOGY.md.
STRONG_AT = 0.90
WEAK_AT = 0.60

LIMITATION = (
    "The learned detector is a single uncalibrated model. Its score is one signal, "
    "not proof, and its thresholds are provisional until tested on this project's "
    "evaluation set."
)


class DetectorError(Exception):
    """Internal: the detector cannot produce a result."""


@dataclass(frozen=True)
class DetectorOutput:
    status: str  # "ok" or "not_determined"
    ai_probability: Optional[float] = None
    reason: Optional[str] = None


def preprocess(image: Image.Image) -> np.ndarray:
    """Convert to RGB, resize to 224x224 (bicubic), scale to [0, 1], normalise,
    and return an NCHW float32 tensor of shape (1, 3, 224, 224)."""
    rgb = image.convert("RGB").resize(
        (DETECTOR_INPUT_SIZE, DETECTOR_INPUT_SIZE), Image.Resampling.BICUBIC
    )
    x = np.asarray(rgb, dtype=np.float32) / 255.0  # H, W, C
    x = (x - MEAN) / STD
    x = np.transpose(x, (2, 0, 1))                 # C, H, W
    return np.ascontiguousarray(x[np.newaxis, ...], dtype=np.float32)


def softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - np.max(logits)  # numerical stability
    exp = np.exp(shifted)
    return exp / exp.sum()


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def interpret_logits(logits) -> DetectorOutput:
    values = np.asarray(logits, dtype=np.float64).reshape(-1)
    if values.shape != (2,) or not np.all(np.isfinite(values)):
        return DetectorOutput("not_determined", reason="Detector returned an unexpected output.")
    probabilities = softmax(values)
    return DetectorOutput("ok", ai_probability=float(probabilities[DETECTOR_ARTIFICIAL_INDEX]))


class OnnxDetector:
    def __init__(self, model_path, expected_sha256=None, timeout=INFERENCE_TIMEOUT_SECONDS):
        self._path = Path(model_path)
        self._expected_sha256 = expected_sha256.lower() if expected_sha256 else None
        self._timeout = timeout
        self._session = None
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="detector")

    @property
    def status(self) -> str:
        return "loaded" if self._session is not None else "not_loaded"

    def _ensure_session(self):
        with self._lock:
            if self._session is None:
                self._session = self._load()
            return self._session

    def _load(self):
        if not self._path.is_file():
            raise DetectorError("Detector model file is missing.")
        if self._expected_sha256 and sha256_of(self._path) != self._expected_sha256:
            raise DetectorError("Detector model checksum does not match.")
        import onnxruntime as ort

        try:
            return ort.InferenceSession(str(self._path), providers=["CPUExecutionProvider"])
        except Exception as exc:
            raise DetectorError("Detector model is not a valid ONNX file.") from exc

    @staticmethod
    def _run(session, tensor):
        input_name = session.get_inputs()[0].name
        return session.run(None, {input_name: tensor})[0]

    def predict(self, image: Image.Image) -> DetectorOutput:
        try:
            session = self._ensure_session()
            tensor = preprocess(image)
            future = self._pool.submit(self._run, session, tensor)
            logits = future.result(timeout=self._timeout)
        except DetectorError as exc:
            return DetectorOutput("not_determined", reason=str(exc))
        except FutureTimeout:
            return DetectorOutput("not_determined", reason="Detector timed out.")
        except Exception:
            return DetectorOutput("not_determined", reason="Detector inference failed.")
        return interpret_logits(logits)


def learned_signal(output: DetectorOutput) -> dict:
    """Convert a detector output into a report signal. Failures stay not_determined."""
    signal = {
        "name": "learned_detector",
        "family": "learned",
        "strength": "not_determined",
        "score": None,
        "reason": None,
        "evidence": {},
        "limitations": [LIMITATION],
    }
    if output.status != "ok" or output.ai_probability is None:
        signal["reason"] = output.reason or "Learned detector did not run."
        return signal

    p = output.ai_probability
    signal["score"] = round(p, 4)
    if p >= STRONG_AT:
        signal["strength"] = "strong"
        signal["reason"] = f"The model estimates a {p:.0%} chance the image was AI-generated (uncalibrated)."
    elif p >= WEAK_AT:
        signal["strength"] = "weak"
        signal["reason"] = f"The model gives a borderline {p:.0%} AI estimate (uncalibrated)."
    else:
        signal["strength"] = "none"
        signal["reason"] = "The model did not flag this image above its threshold. This is not evidence that the image is unedited."
    return signal


@lru_cache(maxsize=1)
def get_detector() -> Optional[OnnxDetector]:
    raw_path = settings.detector_local_path.strip()
    if not raw_path:
        return None
    path = Path(raw_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    expected = settings.detector_sha256.strip() or None
    return OnnxDetector(path, expected_sha256=expected)


def run_learned_detector(image: Image.Image) -> dict:
    """Single entry point for the analysis pipeline. Never raises."""
    try:
        detector = get_detector()
        if detector is None:
            output = DetectorOutput("not_determined", reason="Learned detector is not configured.")
        else:
            output = detector.predict(image)
    except Exception:
        output = DetectorOutput("not_determined", reason="Learned detector failed unexpectedly.")
    return learned_signal(output)