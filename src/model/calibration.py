from __future__ import annotations
import math
import numpy as np

def fit_sigmoid_calibrator(probabilities, labels, epochs=600, learning_rate=0.03):
    if len(probabilities) != len(labels) or len(probabilities) < 30:
        return {"a": 1.0, "b": 0.0, "fitted": False}
    p0 = np.clip(np.asarray(probabilities, dtype=float), 1e-6, 1 - 1e-6)
    x = np.log(p0 / (1.0 - p0))
    y = np.asarray(labels, dtype=float)
    a, b = 1.0, 0.0
    n = float(len(x))
    for _ in range(epochs):
        z = np.clip(a * x + b, -30.0, 30.0)
        p = 1.0 / (1.0 + np.exp(-z))
        e = p - y
        a -= learning_rate * float(np.dot(e, x)) / n
        b -= learning_rate * float(np.sum(e)) / n
    return {"a": round(a, 10), "b": round(b, 10), "fitted": True}

def apply_sigmoid_calibrator(probability, calibration):
    calibration = calibration or {}
    p = min(max(float(probability), 1e-6), 1 - 1e-6)
    x = math.log(p / (1 - p))
    z = max(-30.0, min(30.0, float(calibration.get("a", 1.0)) * x + float(calibration.get("b", 0.0))))
    return 1.0 / (1.0 + math.exp(-z))

def calibration_metrics(probabilities, labels, bins=10):
    if len(probabilities) == 0:
        return {"brier": None, "log_loss": None, "ece": None}
    p = np.clip(np.asarray(probabilities, dtype=float), 1e-6, 1 - 1e-6)
    y = np.asarray(labels, dtype=float)
    brier = float(np.mean((p - y) ** 2))
    log_loss = float(-np.mean(y * np.log(p) + (1.0 - y) * np.log(1.0 - p)))
    ece = 0.0
    for i in range(bins):
        lo, hi = i / bins, (i + 1) / bins
        mask = (p >= lo) & (p < hi if i < bins - 1 else p <= hi)
        if np.any(mask):
            ece += float(np.mean(mask)) * abs(float(np.mean(p[mask])) - float(np.mean(y[mask])))
    return {"brier": round(brier, 6), "log_loss": round(log_loss, 6), "ece": round(ece, 6)}
