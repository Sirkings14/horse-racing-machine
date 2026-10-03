from __future__ import annotations
import math

def fit_sigmoid_calibrator(probabilities, labels, epochs=600, learning_rate=0.03):
    if len(probabilities) != len(labels) or len(probabilities) < 30:
        return {"a": 1.0, "b": 0.0, "fitted": False}
    x = [math.log(min(max(float(p), 1e-6), 1 - 1e-6) / (1 - min(max(float(p), 1e-6), 1 - 1e-6))) for p in probabilities]
    y = [int(v) for v in labels]
    a, b = 1.0, 0.0
    for _ in range(epochs):
        ga = gb = 0.0
        for xi, yi in zip(x, y):
            z = max(-30.0, min(30.0, a * xi + b))
            p = 1.0 / (1.0 + math.exp(-z))
            e = p - yi
            ga += e * xi
            gb += e
        n = float(len(x))
        a -= learning_rate * ga / n
        b -= learning_rate * gb / n
    return {"a": round(a, 10), "b": round(b, 10), "fitted": True}

def apply_sigmoid_calibrator(probability, calibration):
    calibration = calibration or {}
    p = min(max(float(probability), 1e-6), 1 - 1e-6)
    x = math.log(p / (1 - p))
    z = max(-30.0, min(30.0, float(calibration.get("a", 1.0)) * x + float(calibration.get("b", 0.0))))
    return 1.0 / (1.0 + math.exp(-z))

def calibration_metrics(probabilities, labels, bins=10):
    if not probabilities:
        return {"brier": None, "log_loss": None, "ece": None}
    p = [min(max(float(v), 1e-6), 1 - 1e-6) for v in probabilities]
    y = [int(v) for v in labels]
    brier = sum((a - b) ** 2 for a, b in zip(p, y)) / len(p)
    log_loss = -sum(b * math.log(a) + (1 - b) * math.log(1 - a) for a, b in zip(p, y)) / len(p)
    ece = 0.0
    for i in range(bins):
        lo, hi = i / bins, (i + 1) / bins
        members = [j for j, v in enumerate(p) if lo <= v < hi or (i == bins - 1 and v <= hi)]
        if members:
            mean_p = sum(p[j] for j in members) / len(members)
            observed = sum(y[j] for j in members) / len(members)
            ece += len(members) / len(p) * abs(mean_p - observed)
    return {"brier": round(brier, 6), "log_loss": round(log_loss, 6), "ece": round(ece, 6)}
