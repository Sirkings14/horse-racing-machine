from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np

from src.model.feature_engineering import FEATURE_NAMES, build_matrix, standardize_apply, standardize_fit


@dataclass
class OrderModel:
    """Pairwise finishing-order model.

    The model learns which feature differences tend to separate an earlier
    finisher from a later finisher. At inference time the learned horse scores
    are converted into a Plackett-Luce-style sequential order distribution.
    """

    feature_names: List[str]
    mean: List[float]
    std: List[float]
    coefficients: List[float]
    intercept: float = 0.0
    l2: float = 1.0

    def score(self, rows: Sequence[Dict[str, Any]]) -> np.ndarray:
        matrix = build_matrix(rows)
        if len(matrix) == 0:
            return np.empty(0, dtype=float)
        x = standardize_apply(
            matrix,
            np.asarray(self.mean, dtype=float),
            np.asarray(self.std, dtype=float),
        )
        return self.intercept + x @ np.asarray(self.coefficients, dtype=float)

    def predict_order(self, rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        scores = self.score(rows)
        if len(scores) == 0:
            return []

        # Numerical-safe softmax gives a race-relative probability-like weight.
        shifted = np.clip(scores - np.max(scores), -30.0, 30.0)
        weights = np.exp(shifted)
        probabilities = weights / max(float(weights.sum()), 1e-12)

        items: List[Dict[str, Any]] = []
        for row, score, probability in zip(rows, scores, probabilities):
            items.append(
                {
                    "horse_number": int(row["horse_number"]),
                    "horse_name": row.get("horse_name"),
                    "order_score": round(float(score), 6),
                    "order_win_probability": round(float(probability), 6),
                }
            )

        items.sort(key=lambda item: (-item["order_score"], item["horse_number"]))
        for rank, item in enumerate(items, 1):
            item["predicted_finish_position"] = rank
        return items

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_type": "pairwise_finishing_order",
            "feature_names": self.feature_names,
            "mean": self.mean,
            "std": self.std,
            "coefficients": self.coefficients,
            "intercept": self.intercept,
            "l2": self.l2,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "OrderModel":
        return cls(
            feature_names=list(payload["feature_names"]),
            mean=list(payload["mean"]),
            std=list(payload["std"]),
            coefficients=list(payload["coefficients"]),
            intercept=float(payload.get("intercept", 0.0)),
            l2=float(payload.get("l2", 1.0)),
        )


def _sigmoid(values: np.ndarray) -> np.ndarray:
    values = np.clip(values, -30.0, 30.0)
    return 1.0 / (1.0 + np.exp(-values))


def fit_order_model(
    rows: Sequence[Dict[str, Any]],
    epochs: int = 900,
    learning_rate: float = 0.035,
    l2: float = 1.0,
) -> OrderModel:
    """Fit a Bradley-Terry-style pairwise model from verified finish positions."""
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        key = str(row.get("race_key") or "")
        position = row.get("finish_position")
        if not key or position is None:
            continue
        try:
            int(position)
        except (TypeError, ValueError):
            continue
        grouped.setdefault(key, []).append(row)

    pairwise: List[np.ndarray] = []
    targets: List[float] = []
    for race_rows in grouped.values():
        matrix = build_matrix(race_rows)
        positions = []
        for row in race_rows:
            try:
                positions.append(int(row["finish_position"]))
            except (TypeError, ValueError):
                positions.append(10**9)

        for i in range(len(race_rows)):
            for j in range(i + 1, len(race_rows)):
                if positions[i] == positions[j] or positions[i] >= 10**9 or positions[j] >= 10**9:
                    continue
                diff = matrix[i] - matrix[j]
                if positions[i] < positions[j]:
                    pairwise.append(diff)
                    targets.append(1.0)
                else:
                    pairwise.append(-diff)
                    targets.append(1.0)

    if not pairwise:
        raise ValueError("Order model requires verified finish positions with at least one comparable pair.")

    x_raw = np.asarray(pairwise, dtype=float)
    target = np.asarray(targets, dtype=float)
    x, mean, std = standardize_fit(x_raw)

    coefficients = np.zeros(x.shape[1], dtype=float)
    intercept = 0.0
    sample_count = float(len(target))

    for _ in range(epochs):
        probabilities = _sigmoid(intercept + x @ coefficients)
        error = probabilities - target
        grad_intercept = float(error.sum() / sample_count)
        grad_coefficients = (x.T @ error) / sample_count
        grad_coefficients += l2 * coefficients / sample_count
        intercept -= learning_rate * grad_intercept
        coefficients -= learning_rate * grad_coefficients

    return OrderModel(
        feature_names=list(FEATURE_NAMES),
        mean=mean.tolist(),
        std=std.tolist(),
        coefficients=coefficients.tolist(),
        intercept=intercept,
        l2=l2,
    )
