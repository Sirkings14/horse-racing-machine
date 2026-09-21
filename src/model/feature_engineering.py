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
    "commentary_positive_score",
    "commentary_negative_score",
    "commentary_balance_score",
    "commentary_confidence_score",
    "commentary_recentness_score",
    "race_prize_per_runner_score",
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


POSITIVE_TERMS = (
    "excellent", "succès", "victoire", "podium", "forme", "incontournable",
    "base solide", "première chance", "bon rôle", "mérite", "crédit",
    "déclassé", "idéalement engagé", "tout semble réuni", "au top",
)
NEGATIVE_TERMS = (
    "échec", "échoué", "déception", "doute", "sans marge", "moins à l'aise",
    "nettement moins", "aucune marge", "outsider", "reste barré", "limites",
    "difficile", "devra sortir le grand jeu", "ton en dessous",
)
CONFIDENCE_TERMS = (
    "incontournable", "base solide", "première chance", "choix", "mérite",
    "tout semble réuni", "déclassé", "idéalement engagé",
)
RECENCY_TERMS = (
    "vient de", "récemment", "récent", "dernière", "dernier", "cet été",
    "cette saison", "actuellement", "en dernier",
)


def _text_score(text: Any, terms: Sequence[str]) -> float:
    normalized = str(text or "").lower()
    if not normalized:
        return 0.0
    hits = sum(normalized.count(term) for term in terms)
    return min(hits / 3.0, 1.0)


def row_to_features(row: Dict[str, Any]) -> List[float]:
    distance = safe_float(row.get("distance"))
    runners = safe_float(row.get("runners_count"))
    ranking_average = safe_float(row.get("ranking_average"))
    presence = safe_float(row.get("ranking_presence"))
    prize = safe_float(row.get("prize_euros"))
    runners_safe = max(runners, 1.0)
    description = row.get("horse_description")

    commentary_positive = _text_score(description, POSITIVE_TERMS)
    commentary_negative = _text_score(description, NEGATIVE_TERMS)
    commentary_balance = commentary_positive - commentary_negative
    commentary_confidence = _text_score(description, CONFIDENCE_TERMS)
    commentary_recentness = _text_score(description, RECENCY_TERMS)
    prize_per_runner = min((prize / runners_safe) / 10000.0, 2.0)

    return [
        inverse_rank(row.get("favorites_rank")),
        inverse_rank(row.get("form_rank")),
        inverse_rank(row.get("class_rank")),
        inverse_rank(row.get("progress_rank")),
        inverse_rank(row.get("regularity_rank")),
        inverse_rank(ranking_average, max_rank=10.0),
        min(presence / 5.0, 1.0),
        min(distance / 3000.0, 2.0),
        min(runners / 20.0, 2.0),
        commentary_positive,
        commentary_negative,
        commentary_balance,
        commentary_confidence,
        commentary_recentness,
        prize_per_runner,
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
