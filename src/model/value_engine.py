from __future__ import annotations

from typing import Any


def evaluate_market_value(probability: float, decimal_odds: float) -> dict[str, Any]:
    """Compare an independently supplied probability with a market price."""
    probability = float(probability)
    decimal_odds = float(decimal_odds)
    if not 0 <= probability <= 1:
        raise ValueError("probability must be between 0 and 1")
    if decimal_odds <= 1:
        raise ValueError("decimal_odds must be greater than 1")

    implied_probability = 1.0 / decimal_odds
    edge = probability - implied_probability
    expected_value = probability * decimal_odds - 1.0

    return {
        "probability": probability,
        "decimal_odds": decimal_odds,
        "implied_probability": implied_probability,
        "edge": edge,
        "expected_value": expected_value,
        "positive_value": expected_value > 0,
    }
