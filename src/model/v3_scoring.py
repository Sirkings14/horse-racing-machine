from __future__ import annotations

import math
from statistics import pstdev
from typing import Sequence


def weighted_outcome_score(
    winner_probability: float,
    top3_probability: float,
    top5_probability: float,
) -> float:
    """Return the shared ranking score used by training backtests and live inference.

    This is a ranking score, not a calibrated probability. The three inputs refer
    to different events, so their numeric spread must not be interpreted as model
    disagreement.
    """
    values = (float(winner_probability), float(top3_probability), float(top5_probability))
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Outcome probabilities must be finite.")
    return 0.25 * values[0] + 0.50 * values[1] + 0.25 * values[2]


def rank_percentiles(
    probabilities: Sequence[float],
    horse_numbers: Sequence[int],
) -> list[float]:
    """Map a model's within-race order to [0, 1], best first; ties break by horse number."""
    if len(probabilities) != len(horse_numbers):
        raise ValueError("Probability count must match horse-number count.")
    count = len(probabilities)
    if not count:
        return []

    normalized = []
    for value in probabilities:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("Ranking probabilities must be finite.")
        normalized.append(number)

    order = sorted(
        range(count),
        key=lambda index: (-normalized[index], int(horse_numbers[index])),
    )
    denominator = max(count - 1, 1)
    percentile_by_index = [0.0] * count
    for rank, index in enumerate(order):
        percentile_by_index[index] = rank / denominator
    return percentile_by_index


def rank_disagreement(
    probability_vectors: Sequence[Sequence[float]],
    horse_numbers: Sequence[int],
) -> list[float]:
    """Per-horse disagreement across models with different target scales, measured by rank."""
    vectors = list(probability_vectors)
    if not vectors:
        return [0.0] * len(horse_numbers)
    percentiles = [rank_percentiles(values, horse_numbers) for values in vectors]
    if not percentiles:
        return [0.0] * len(horse_numbers)
    return [
        pstdev(model_ranks[index] for model_ranks in percentiles)
        for index in range(len(horse_numbers))
    ]
