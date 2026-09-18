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
    """Operational health layer: measure live confidence, recent outcomes and model risk."""
    evaluations = _load(EVALUATION_FILE, [])
    if not isinstance(evaluations, list):
        evaluations = []

    sample = evaluations[-50:]
    n = len(sample)

    def rate(metric: str) -> float | None:
        if not n:
            return None
        return round(sum(bool(item.get("metrics", {}).get(metric)) for item in sample) / n, 4)

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
    if prediction:
        monitor = prediction.get("monitoring") or {}
        agreement = monitor.get("agreement")
        ranked = prediction.get("ranked_horses") or []
        margin = 0.0
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

    return {
        "health": health,
        "recent_verified_predictions": n,
        "recent_winner_hit_rate": rate("winner_hit"),
        "recent_winner_in_top3_rate": rate("winner_in_top3"),
        "recent_order_engine_winner_hit_rate": rate("order_engine_winner_hit"),
        "recent_exact_top3_order_rate": rate("exact_top3_order"),
        "recent_exact_top5_order_rate": rate("exact_top5_order"),
        "recent_recommended_hit_average": round(
            sum(float(item.get("metrics", {}).get("recommended_hit_count", 0)) for item in sample) / n, 3
        ) if n else None,
        "order_walk_forward_pairwise_accuracy": pairwise,
        "feature_drift_severity": drift_severity,
        "prediction_confidence": confidence,
        "confidence_reasons": reasons,
        "guard_policy": {
            "never_claim_certainty": True,
            "low_confidence_predictions_are_flagged": True,
            "order_engine_below_random_baseline_is_not_promoted": True,
            "severe_feature_drift_is_flagged": True,
        },
    }


def main() -> dict[str, Any]:
    report = build_autopilot_guard()
    path = BASE_DIR / "data" / "model" / "autopilot_guard.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("AUTOPILOT GUARD")
    print(f"Health: {report['health']}")
    print(f"Verified predictions: {report['recent_verified_predictions']}")
    print(f"Recent winner hit rate: {report['recent_winner_hit_rate']}")
    print(f"Order holdout pairwise accuracy: {report['order_walk_forward_pairwise_accuracy']}")
    return report


if __name__ == "__main__":
    main()
