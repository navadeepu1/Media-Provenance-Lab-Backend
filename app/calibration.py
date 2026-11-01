"""Small, dependency-free calibration utilities for detector probabilities."""

from __future__ import annotations

import math
from typing import Iterable


def fit_platt(scores: Iterable[float], labels: Iterable[int], iterations: int = 100) -> tuple[float, float]:
    values = list(scores)
    targets = list(labels)
    if len(values) != len(targets) or len(values) < 2 or len(set(targets)) != 2:
        raise ValueError("Calibration needs matching scores and both binary classes.")
    logits = [math.log(min(1 - 1e-6, max(1e-6, score)) /
                      (1 - min(1 - 1e-6, max(1e-6, score)))) for score in values]
    a, b = 1.0, 0.0
    for _ in range(iterations):
        probabilities = [1 / (1 + math.exp(-(a * x + b))) for x in logits]
        g_a = sum((p - y) * x for p, y, x in zip(probabilities, targets, logits))
        g_b = sum(p - y for p, y in zip(probabilities, targets))
        h_aa = sum(p * (1 - p) * x * x for p, x in zip(probabilities, logits)) + 1e-8
        h_ab = sum(p * (1 - p) * x for p, x in zip(probabilities, logits))
        h_bb = sum(p * (1 - p) for p in probabilities) + 1e-8
        determinant = h_aa * h_bb - h_ab * h_ab
        if determinant <= 0:
            break
        delta_a = (h_bb * g_a - h_ab * g_b) / determinant
        delta_b = (-h_ab * g_a + h_aa * g_b) / determinant
        a -= delta_a
        b -= delta_b
        if abs(delta_a) + abs(delta_b) < 1e-7:
            break
    return a, b


def apply_platt(score: float, scale: float, offset: float) -> float:
    logit = math.log(min(1 - 1e-6, max(1e-6, score)) /
                     (1 - min(1 - 1e-6, max(1e-6, score))))
    calibrated = 1 / (1 + math.exp(-(scale * logit + offset)))
    return min(1 - 1e-6, max(1e-6, calibrated))
