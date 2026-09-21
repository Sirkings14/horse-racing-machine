from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence, Tuple

import numpy as np


FEATURE_NAMES = [
    "favorites_score",
    "form_score",
    "class_score",
    "progress_score",
    "regularity_score",
    "ranking_average_score",
    "ranking_presence_score",
    "distance_score",
    "field_size_score",
    "core_consensus_score",
    "rank_disagreement_score",
    "market_form_gap",
    "form_class_gap",
    "class_progress_gap",
    "distance_field_interaction",
]


def safe_float(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def inverse_rank(value: Any, max_rank: float = 10.0) -> float:
    rank = safe_float(value)
    if rank <= 0:
        return 0.0
    return max(0.0, (max_rank + 1.0 - min(rank, max_rank)) / max_rank)


def row_to_features(row: Dict[str, Any]) -> List[float]:
    distance = safe_float(row.get("distance"))
    runners = safe_float(row.get("runners_count"))
    ranking_average = safe_float(row.get("ranking_average"))
    presence = safe_float(row.get("ranking_presence"))

    favorites = inverse_rank(row.get("favorites_rank"))
    form = inverse_rank(row.get("form_rank"))
    class_score = inverse_rank(row.get("class_rank"))
    progress = inverse_rank(row.get("progress_rank"))
    regularity = inverse_rank(row.get("regularity_rank"))
    core = np.asarray([favorites, form, class_score, progress, regularity], dtype=float)
    consensus = float(np.mean(core))
    disagreement = float(np.std(core))

    return [
        favorites,
        form,
        class_score,
        progress,
        regularity,
        inverse_rank(ranking_average, max_rank=10.0),
        min(presence / 5.0, 1.0),
        min(distance / 3000.0, 2.0),
        min(runners / 20.0, 2.0),
        consensus,
        disagreement,
        favorites - form,
        form - class_score,
        class_score - progress,
        min(distance / 3000.0, 2.0) * min(runners / 20.0, 2.0),
    ]


def build_matrix(rows: Sequence[Dict[str, Any]]) -> np.ndarray:
    if not rows:
        return np.empty((0, len(FEATURE_NAMES)), dtype=float)
    return np.asarray([row_to_features(row) for row in rows], dtype=float)


def standardize_fit(x: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    mean = x.mean(axis=0) if len(x) else np.zeros(x.shape[1], dtype=float)
    std = x.std(axis=0) if len(x) else np.ones(x.shape[1], dtype=float)
    std = np.where(std < 1e-9, 1.0, std)
    return (x - mean) / std, mean, std


def standardize_apply(x: np.ndarray, mean: np.ndarray, std: np.ndarray) -> np.ndarray:
    safe_std = np.where(std < 1e-9, 1.0, std)
    return (x - mean) / safe_std


def rows_by_race(rows: Iterable[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        key = str(row.get("race_key") or "")
        if key:
            grouped.setdefault(key, []).append(row)
    return grouped
