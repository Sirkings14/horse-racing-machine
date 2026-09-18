from __future__ import annotations

import json
import shutil
from pathlib import Path

from src.model.model_registry import CHALLENGER_DIR, MODEL_DIR, load_registry, promote_candidate

BASE_DIR = Path(__file__).resolve().parents[2]
BACKTEST_FILE = MODEL_DIR / "backtest_report.json"
ORDER_BACKTEST_FILE = MODEL_DIR / "order_backtest_report.json"


def _order_engine_passes() -> bool:
    """Only replace the production order engine after a genuine holdout signal."""
    try:
        report = json.loads(ORDER_BACKTEST_FILE.read_text(encoding="utf-8"))
        metrics = report.get("metrics") or {}
        pairwise = float(metrics["pairwise_order_accuracy"])
        return pairwise > 0.50
    except (OSError, ValueError, TypeError, KeyError):
        return False


def main(candidate_version: str | None = None) -> bool:
    registry = load_registry()
    version = candidate_version
    if not version:
        candidates = [item for item in registry.get("history", []) if item.get("status") == "candidate"]
        if not candidates:
            print("No challenger candidate available for promotion.")
            return False
        version = candidates[-1]["version"]

    candidate_dir = CHALLENGER_DIR / version
    if not candidate_dir.exists():
        print(f"Candidate directory missing: {candidate_dir}")
        return False

    try:
        report = json.loads(BACKTEST_FILE.read_text(encoding="utf-8"))
    except Exception as error:
        print(f"Cannot promote without a valid backtest report: {error}")
        return False

    metrics = report.get("metrics") or {}
    required = (
        "winner_hit_rate_at_1",
        "winner_hit_rate_at_3",
        "average_actual_top3_covered_by_predicted_top3",
    )
    if any(key not in metrics for key in required):
        print("Backtest report is missing required promotion metrics.")
        return False

    champion_metrics = {}
    for item in registry.get("history", []):
        if item.get("version") == registry.get("champion_version"):
            champion_metrics = item.get("metrics") or {}
            break

    if champion_metrics:
        candidate_score = (
            float(metrics["winner_hit_rate_at_3"]),
            float(metrics["average_actual_top3_covered_by_predicted_top3"]),
            float(metrics["winner_hit_rate_at_1"]),
        )
        champion_score = (
            float(champion_metrics.get("winner_hit_rate_at_3", -1)),
            float(champion_metrics.get("average_actual_top3_covered_by_predicted_top3", -1)),
            float(champion_metrics.get("winner_hit_rate_at_1", -1)),
        )
        if candidate_score < champion_score:
            print(f"Challenger {version} rejected: backtest metrics did not improve on champion.")
            return False
        if candidate_score == champion_score:
            print(f"Challenger {version} kept in shadow: no measured improvement over champion.")
            return False

    for depth in (3, 4, 5):
        source = candidate_dir / f"top{depth}_model.json"
        target = MODEL_DIR / f"top{depth}_model.json"
        if not source.exists():
            print(f"Candidate missing Top-{depth} model.")
            return False
        shutil.copy2(source, target)

    order_source = candidate_dir / "order_model.json"
    if order_source.exists() and _order_engine_passes():
        shutil.copy2(order_source, MODEL_DIR / "order_model.json")
        print("Promoted finishing-order model: holdout pairwise accuracy > 0.50.")
    elif order_source.exists():
        print("Order engine kept in shadow: holdout pairwise accuracy did not clear 0.50.")
    else:
        print("Warning: candidate has no finishing-order model; retaining existing order model.")

    promote_candidate(version, metrics)
    print(f"Promoted challenger {version} to champion.")
    return True


if __name__ == "__main__":
    main()
