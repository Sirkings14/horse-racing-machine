from __future__ import annotations

from typing import Any, Dict, List, Sequence


def _numbers(items: Sequence[Dict[str, Any]], key: str, limit: int = 5) -> List[int]:
    return [int(item["horse_number"]) for item in items[:limit]]


def build_race_monitor(
    ranked_horses: Sequence[Dict[str, Any]],
    order_ranking: Sequence[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """Compare the strength ensemble with the independent order engine.

    This layer deliberately reports disagreement instead of hiding it. It is
    a monitoring/decision-support layer, not a guarantee of race outcomes.
    """
    strength = list(ranked_horses)
    order = list(order_ranking or [])
    strength_top5 = _numbers(strength, "ensemble_score")
    order_top5 = _numbers(order, "order_score") if order else []

    strength_top3 = set(strength_top5[:3])
    order_top3 = set(order_top5[:3])
    common_top3 = sorted(strength_top3 & order_top3)
    common_top5 = sorted(set(strength_top5) & set(order_top5))

    winner_candidate = strength_top5[0] if strength_top5 else None
    order_winner = order_top5[0] if order_top5 else None

    if not order:
        agreement = "order_engine_unavailable"
    elif winner_candidate == order_winner:
        agreement = "strong_agreement"
    elif len(common_top3) >= 2:
        agreement = "partial_agreement"
    else:
        agreement = "meaningful_disagreement"

    return {
        "status": "monitoring_complete",
        "strength_engine_top5": strength_top5,
        "order_engine_top5": order_top5,
        "strength_engine_winner_candidate": winner_candidate,
        "order_engine_winner_candidate": order_winner,
        "common_top3": common_top3,
        "common_top5": common_top5,
        "agreement": agreement,
        "agreement_score_top5": round(len(common_top5) / max(min(5, len(strength_top5), len(order_top5)), 1), 4) if order else None,
        "warning": (
            "Independent engines disagree; treat exact order as lower-confidence."
            if agreement == "meaningful_disagreement"
            else None
        ),
    }
