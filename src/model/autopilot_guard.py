from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[2]
EVALUATION_FILE = BASE_DIR / "data" / "evaluation" / "prediction_evaluations.json"
DRIFT_FILE = BASE_DIR / "data" / "model" / "feature_drift_report.json"
ORDER_BACKTEST_FILE = BASE_DIR / "data" / "model" / "order_backtest_report.json"


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def build_autopilot_guard(prediction: dict[str, Any] | None = None) -> dict[str, Any]:
    """Operational health and pre-race PASS/PLAY_CANDIDATE gate.

    The gate is deliberately conservative. It never claims certainty and
    returns PASS when the live evidence is too weak or internally unstable.
    """
    evaluations = _load(EVALUATION_FILE, [])
    if not isinstance(evaluations, list):
        evaluations = []

    sample = evaluations[-50:]
    n = len(sample)

    def rate(metric: str) -> float | None:
        if not n:
            return None
        return round(sum(bool(item.get("metrics", {}).get(metric)) for item in sample) / n, 4)

    def engine_rate(engine: str, metric: str) -> float | None:
        if not n:
            return None
        hits = counted = 0
        for item in sample:
            engine_metrics = item.get("metrics", {}).get("engine_attribution", {}).get(engine)
            if isinstance(engine_metrics, dict) and metric in engine_metrics:
                counted += 1
                hits += bool(engine_metrics.get(metric))
        return round(hits / counted, 4) if counted else None

    def engine_average(engine: str, metric: str) -> float | None:
        values: list[float] = []
        for item in sample:
            engine_metrics = item.get("metrics", {}).get("engine_attribution", {}).get(engine, {})
            if metric in engine_metrics:
                try:
                    values.append(float(engine_metrics[metric]))
                except (TypeError, ValueError):
                    pass
        return round(sum(values) / len(values), 3) if values else None

    engine_metrics = {
        engine: {
            "winner_hit_rate": engine_rate(engine, "winner_hit"),
            "winner_in_top3_rate": engine_rate(engine, "winner_in_top3"),
            "winner_in_top5_rate": engine_rate(engine, "winner_in_top5"),
            "avg_actual_top3_covered_by_top3": engine_average(engine, "actual_top3_covered_by_top3"),
            "avg_actual_top3_covered_by_top5": engine_average(engine, "actual_top3_covered_by_top5"),
            "avg_actual_top5_covered_by_top5": engine_average(engine, "actual_top5_covered_by_top5"),
            "exact_top3_order_rate": engine_rate(engine, "exact_top3_order"),
            "exact_top5_order_rate": engine_rate(engine, "exact_top5_order"),
            "avg_top5_position_hits": engine_average(engine, "top5_position_hits"),
        }
        for engine in ("strength", "order", "fused")
    }

    drift = _load(DRIFT_FILE, {})
    drift_severity = drift.get("overall_severity") if isinstance(drift, dict) else None

    order_report = _load(ORDER_BACKTEST_FILE, {})
    order_metrics = order_report.get("metrics") if isinstance(order_report, dict) else {}
    pairwise = order_metrics.get("pairwise_order_accuracy")

    health = "insufficient_history"
    if n >= 10:
        health = "stable_observation"
    if n >= 20 and rate("winner_hit") is not None and rate("winner_hit") < 0.10:
        health = "degraded_winner_accuracy"
    if n >= 20 and pairwise is not None and float(pairwise) < 0.50:
        health = "degraded_order_engine"
    if drift_severity == "severe":
        health = "severe_feature_drift"

    confidence = "unrated"
    reasons: list[str] = []
    margin = 0.0
    agreement = None
    difficulty = {}
    if prediction:
        monitor = prediction.get("monitoring") or {}
        agreement = monitor.get("agreement")
        difficulty = prediction.get("difficulty") or {}
        ranked = prediction.get("ranked_horses") or []
        if len(ranked) >= 2:
            margin = float(ranked[0].get("probability_top3", 0.0)) - float(ranked[1].get("probability_top3", 0.0))
        if agreement == "strong_agreement" and margin >= 0.05:
            confidence = "high"
        elif agreement == "meaningful_disagreement" or margin < 0.02:
            confidence = "low"
            if agreement == "meaningful_disagreement":
                reasons.append("independent engines disagree")
            if margin < 0.02:
                reasons.append("top candidates are tightly separated")
        else:
            confidence = "medium"

    gate_reasons: list[str] = []
    # These are safety/data-quality gates, not claims about race outcome.
    if n < 20:
        gate_reasons.append("insufficient_verified_history")
    if drift_severity == "severe":
        gate_reasons.append("severe_feature_drift")
    if prediction and agreement == "order_engine_unavailable":
        gate_reasons.append("engine_disagreement_or_unavailable")
    if prediction and confidence == "low":
        gate_reasons.append("low_model_confidence")
    if prediction and difficulty.get("bucket") == "high":
        gate_reasons.append("high_race_difficulty")
    if prediction and len((prediction.get("ranked_horses") or [])) < 5:
        gate_reasons.append("insufficient_race_field_data")
    if n >= 20 and rate("winner_hit") is not None and rate("winner_hit") < 0.10:
        gate_reasons.append("recent_winner_accuracy_degraded")
    if n >= 20 and pairwise is not None and float(pairwise) < 0.50:
        gate_reasons.append("order_engine_below_random_baseline")

    decision = "PASS" if gate_reasons else "PLAY_CANDIDATE"

    return {
        "health": health,
        "decision": decision,
        "gate_reasons": gate_reasons,
        "recent_verified_predictions": n,
        "recent_winner_hit_rate": rate("winner_hit"),
        "recent_winner_in_top3_rate": rate("winner_in_top3"),
        "recent_order_engine_winner_hit_rate": rate("order_engine_winner_hit"),
        "recent_exact_top3_order_rate": rate("exact_top3_order"),
        "recent_exact_top5_order_rate": rate("exact_top5_order"),
        "recent_recommended_hit_average": round(
            sum(float(item.get("metrics", {}).get("recommended_hit_count", 0)) for item in sample) / n, 3
        ) if n else None,
        "engine_attribution": engine_metrics,
        "order_walk_forward_pairwise_accuracy": pairwise,
        "feature_drift_severity": drift_severity,
        "prediction_confidence": confidence,
        "confidence_reasons": reasons,
        "difficulty": difficulty,
        "gate_policy": {
            "PASS_means_insufficient_or_unstable_evidence": True,
            "PLAY_CANDIDATE_is_not_a_guarantee_of_outcome_or_profit": True,
            "insufficient_verified_history_blocks": True,
            "severe_feature_drift_blocks": True,
            "low_confidence_blocks": True,
            "engine_disagreement_blocks": True,
            "high_difficulty_blocks": True,
            "degraded_recent_winner_accuracy_blocks": True,
            "order_engine_below_random_baseline_blocks": True,
        },
    }


def main() -> dict[str, Any]:
    report = build_autopilot_guard()
    path = BASE_DIR / "data" / "model" / "autopilot_guard.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("AUTOPILOT GUARD")
    print(f"Decision: {report['decision']}")
    print(f"Health: {report['health']}")
    print(f"Verified predictions: {report['recent_verified_predictions']}")
    print(f"Recent winner hit rate: {report['recent_winner_hit_rate']}")
    print(f"Order holdout pairwise accuracy: {report['order_walk_forward_pairwise_accuracy']}")
    print(f"Gate reasons: {report['gate_reasons']}")
    return report


if __name__ == "__main__":
    main()
