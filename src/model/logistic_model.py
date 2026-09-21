from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Sequence

import numpy as np

from src.model.feature_engineering import (
    FEATURE_NAMES,
    build_matrix,
    standardize_apply,
    standardize_fit,
)


@dataclass
class LogisticModel:
    feature_names: List[str]
    mean: List[float]
    std: List[float]
    intercept: float
    coefficients: List[float]
    positive_weight: float
    l2: float = 1.0

    def predict_weighted_proba(self, rows: Sequence[Dict[str, Any]]) -> np.ndarray:
        matrix = build_matrix(rows)
        if len(matrix) == 0:
            return np.empty(0, dtype=float)
        x = standardize_apply(
            matrix,
            np.asarray(self.mean, dtype=float),
            np.asarray(self.std, dtype=float),
        )
        logits = self.intercept + x @ np.asarray(self.coefficients, dtype=float)
        logits = np.clip(logits, -30.0, 30.0)
        return 1.0 / (1.0 + np.exp(-logits))

    def predict_proba(self, rows: Sequence[Dict[str, Any]]) -> np.ndarray:
        # Positive examples are up-weighted during training. Correct the
        # posterior back to the observed class prior before using it as a
        # probability.
        weighted = self.predict_weighted_proba(rows)
        weight = max(float(self.positive_weight), 1e-12)
        denominator = weight * (1.0 - weighted) + weighted
        return np.clip(weighted / np.maximum(denominator, 1e-12), 0.0, 1.0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_names": self.feature_names,
            "mean": self.mean,
            "std": self.std,
            "intercept": self.intercept,
            "coefficients": self.coefficients,
            "positive_weight": self.positive_weight,
            "l2": self.l2,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "LogisticModel":
        return cls(
            feature_names=list(payload["feature_names"]),
            mean=list(payload["mean"]),
            std=list(payload["std"]),
            intercept=float(payload["intercept"]),
            coefficients=list(payload["coefficients"]),
            positive_weight=float(payload.get("positive_weight", 1.0)),
            l2=float(payload.get("l2", 1.0)),
        )


def _sigmoid(values: np.ndarray) -> np.ndarray:
    values = np.clip(values, -30.0, 30.0)
    return 1.0 / (1.0 + np.exp(-values))


def fit_top3_model(
    rows: Sequence[Dict[str, Any]],
    target_field: str = "top3",
    epochs: int = 1200,
    learning_rate: float = 0.04,
    l2: float = 1.0,
) -> LogisticModel:
    if not rows:
        raise ValueError("Cannot train a model with no rows.")

    matrix = build_matrix(rows)
    target = np.asarray(
        [1.0 if int(row.get(target_field, 0)) == 1 else 0.0 for row in rows],
        dtype=float,
    )

    positive = float(target.sum())
    negative = float(len(target) - positive)
    if positive <= 0 or negative <= 0:
        raise ValueError("Training data must contain both positive and negative examples.")

    x, mean, std = standardize_fit(matrix)
    weights = np.where(target > 0.5, negative / positive, 1.0)

    intercept = float(np.log(positive / negative))
    coefficients = np.zeros(x.shape[1], dtype=float)

    sample_count = float(len(target))

    for _ in range(epochs):
        probabilities = _sigmoid(intercept + x @ coefficients)
        error = probabilities - target
        weighted_error = error * weights

        grad_intercept = float(weighted_error.sum() / sample_count)
        grad_coefficients = (x.T @ weighted_error) / sample_count
        grad_coefficients += l2 * coefficients / sample_count

        intercept -= learning_rate * grad_intercept
        coefficients -= learning_rate * grad_coefficients

    return LogisticModel(
        feature_names=list(FEATURE_NAMES),
        mean=mean.tolist(),
        std=std.tolist(),
        intercept=intercept,
        coefficients=coefficients.tolist(),
        positive_weight=negative / positive,
        l2=l2,
    )
