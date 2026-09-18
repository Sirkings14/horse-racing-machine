from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Sequence

import numpy as np

from src.model.feature_engineering import FEATURE_NAMES, build_matrix, standardize_apply, standardize_fit


@dataclass
class OrderModel:
    """Pairwise finishing-order model trained only on verified finish positions."""

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
        x = standardize_apply(matrix, np.asarray(self.mean), np.asarray(self.std))
        return self.intercept + x @ np.asarray(self.coefficients)

    def predict_order(self, rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        scores = self.score(rows)
        if len(scores) == 0:
            return []
        shifted = np.clip(scores - np.max(scores), -30.0, 30.0)
        weights = np.exp(shifted)
        probabilities = weights / max(float(weights.sum()), 1e-12)
        items = []
        for row, score, probability in zip(rows, scores, probabilities):
            items.append({
                "horse_number": int(row["horse_number"]),
                "horse_name": row.get("horse_name"),
                "order_score": round(float(score), 6),
                "order_win_probability": round(float(probability), 6),
            })
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
    epochs: int = 250,
    learning_rate: float = 0.06,
    l2: float = 1.0,
) -> OrderModel:
    """Fit a Bradley-Terry-style pairwise model in a consistent standardized feature space."""
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

    if not grouped:
        raise ValueError("Order model requires verified finish positions.")

    all_rows = [row for race_rows in grouped.values() for row in race_rows]
    raw_matrix = build_matrix(all_rows)
    _, mean, std = standardize_fit(raw_matrix)

    pairwise = []
    for race_rows in grouped.values():
        matrix = standardize_apply(build_matrix(race_rows), mean, std)
        positions = []
        for row in race_rows:
            try:
                positions.append(int(row["finish_position"]))
            except (TypeError, ValueError):
                positions.append(10**9)
        for i in range(len(race_rows)):
            for j in range(i + 1, len(race_rows)):
                if positions[i] >= 10**9 or positions[j] >= 10**9 or positions[i] == positions[j]:
                    continue
                if positions[i] < positions[j]:
                    pairwise.append(matrix[i] - matrix[j])
                else:
                    pairwise.append(matrix[j] - matrix[i])

    if not pairwise:
        raise ValueError("Order model requires comparable verified pairs.")

    x = np.asarray(pairwise, dtype=float)
    target = np.ones(len(x), dtype=float)
    coefficients = np.zeros(x.shape[1], dtype=float)
    intercept = 0.0
    sample_count = float(len(target))

    for _ in range(epochs):
        probabilities = _sigmoid(intercept + x @ coefficients)
        error = probabilities - target
        grad_intercept = float(error.mean())
        grad_coefficients = (x.T @ error) / sample_count + l2 * coefficients / sample_count
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
