from __future__ import annotations

from typing import Any
import math

from src.model.market_evidence import latest_observed_snapshot
from src.model.v3_model import normalize_race_probabilities


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def score_race_opportunity(
    ranked_horses: list[dict[str, Any]],
    market_odds: dict[int, float] | None = None,
) -> dict[str, Any]:
    """Score race quality separately from horse ranking.

    Market prices are optional and must be explicitly observed. No price is
    inferred from model probabilities. The score is a triage layer, not a
    betting guarantee.
    """
    top = ranked_horses[:5]
    if not top:
        return {
            "tier": "UNRATED",
            "model_quality_score": 0.0,
            "market_edge_available": False,
            "value_candidates": [],
            "reasons": ["no_ranked_horses"],
        }

    top3 = _mean([float(x.get("probability_top3", 0.0)) for x in top])
    top5 = _mean([float(x.get("probability_top5", 0.0)) for x in top])
    margin = max(0.0, float(top[0].get("ensemble_score", 0.0)) - float(top[1].get("ensemble_score", 0.0))) if len(top) > 1 else 0.0
    agreement = 1.0 - _mean([float(x.get("model_disagreement", 1.0)) for x in top])
    completeness = _mean([float(x.get("data_completeness", 0.0)) for x in top])

    # Bounded components keep the race score comparable across fields.
    quality = 100.0 * (
        0.40 * min(max(top3, 0.0), 1.0)
        + 0.20 * min(max(top5, 0.0), 1.0)
        + 0.15 * min(margin / 0.10, 1.0)
        + 0.15 * min(max(agreement, 0.0), 1.0)
        + 0.10 * min(max(completeness, 0.0), 1.0)
    )

    values: list[dict[str, Any]] = []
    evidence_source = None
    evidence_captured_at = None
    if market_odds is None and ranked_horses and ranked_horses[0].get("race_key"):
        snapshot = latest_observed_snapshot(str(ranked_horses[0]["race_key"]), "winner")
        if snapshot:
            market_odds = snapshot.get("odds") or {}
            evidence_source = snapshot.get("source")
            evidence_captured_at = snapshot.get("captured_at")

    normalized_winner_probabilities: list[float] | None = None
    try:
        raw_winner_probabilities = [float(horse.get("probability_winner")) for horse in ranked_horses]
        normalized_winner_probabilities = normalize_race_probabilities(raw_winner_probabilities).tolist()
    except (TypeError, ValueError, OverflowError):
        # Invalid win-probability mass must never create an apparent value edge.
        normalized_winner_probabilities = None

    if isinstance(market_odds, dict) and normalized_winner_probabilities is not None:
        normalized_odds: dict[int, float] = {}
        for raw_number, raw_price in market_odds.items():
            try:
                number = int(raw_number)
                odds = float(raw_price)
            except (TypeError, ValueError, OverflowError):
                continue
            if number > 0 and math.isfinite(odds) and odds > 1.0:
                normalized_odds[number] = odds

        for index, horse in enumerate(ranked_horses[:5]):
            try:
                number = int(horse["horse_number"])
                raw_probability = float(horse.get("probability_winner", 0.0))
            except (TypeError, ValueError, OverflowError):
                continue
            odds = normalized_odds.get(number)
            if odds is None:
                continue
            probability = float(normalized_winner_probabilities[index])
            implied = 1.0 / odds
            edge = probability - implied
            values.append({
                "horse_number": number,
                "observed_decimal_odds": round(odds, 4),
                "probability_winner": round(probability, 6),
                "raw_model_probability_winner": round(raw_probability, 6),
                "implied_probability": round(implied, 6),
                "edge": round(edge, 6),
            })

    values.sort(key=lambda x: (-x["edge"], x["horse_number"]))
    if quality >= 72:
        tier = "A"
    elif quality >= 58:
        tier = "B"
    elif quality >= 44:
        tier = "C"
    else:
        tier = "D"

    reasons = []
    if margin >= 0.05:
        reasons.append("clear_top_candidate")
    elif margin < 0.02:
        reasons.append("tight_top_candidates")
    if agreement >= 0.94:
        reasons.append("low_model_disagreement")
    elif agreement < 0.88:
        reasons.append("elevated_model_disagreement")
    if completeness >= 0.99:
        reasons.append("complete_pre_race_data")
    if values:
        positive = sum(1 for x in values if x["edge"] > 0)
        reasons.append("observed_market_prices_available")
        if positive:
            reasons.append("positive_model_market_edges_present")

    return {
        "tier": tier,
        "model_quality_score": round(quality, 2),
        "market_edge_available": bool(values),
        "market_evidence_source": evidence_source,
        "market_evidence_captured_at": evidence_captured_at,
        "value_candidates": values,
        "top_candidate_margin": round(margin, 6),
        "top5_mean_top3_probability": round(top3, 6),
        "top5_mean_top5_probability": round(top5, 6),
        "top5_mean_model_agreement": round(agreement, 6),
        "top5_mean_data_completeness": round(completeness, 6),
        "reasons": reasons,
        "policy": {
            "race_quality_is_not_profitability": True,
            "market_prices_must_be_observed": True,
            "probabilities_are_not_prices": True,
            "winner_probabilities_are_race_normalized": True,
            "normalization_does_not_prove_calibration": True,
            "market_edge_does_not_authorize_betting": True,
        },
    }
