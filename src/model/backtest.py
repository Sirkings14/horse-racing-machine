from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Sequence

from src.model.logistic_model import fit_top3_model


BASE_DIR = Path(__file__).resolve().parents[2]
DATASET_FILE = BASE_DIR / "data" / "dataset" / "training_dataset_clean.json"
OUTPUT_FILE = BASE_DIR / "data" / "model" / "backtest_report.json"


def load_rows() -> List[Dict[str, Any]]:
    with DATASET_FILE.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError("Clean training dataset must be a JSON list.")
    return data


def race_sort_key(race_key: str) -> tuple:
    date, track, race_number = race_key.split("|", 2)
    return date, track, int(race_number)


def rank_rows(rows: Sequence[Dict[str, Any]], probabilities: Sequence[float]) -> List[Dict[str, Any]]:
    ranked = []
    for row, probability in zip(rows, probabilities):
        item = dict(row)
        item["predicted_probability"] = float(probability)
        ranked.append(item)
    return sorted(
        ranked,
        key=lambda row: (-row["predicted_probability"], row.get("horse_number", 9999)),
    )


def binary_calibration_metrics(probabilities: Sequence[float], labels: Sequence[int], bins: int = 10) -> Dict[str, Any]:
    """Measure whether model scores behave like probabilities; ranking is unaffected."""
    import math
    if not probabilities:
        return {"brier_score": None, "log_loss": None, "ece": None, "calibration_bins": []}
    p = [min(max(float(value), 1e-6), 1.0 - 1e-6) for value in probabilities]
    y = [int(value) for value in labels]
    brier = sum((prob - label) ** 2 for prob, label in zip(p, y)) / len(y)
    log_loss = -sum(label * math.log(prob) + (1 - label) * math.log(1 - prob) for prob, label in zip(p, y)) / len(y)
    calibration_bins = []
    ece = 0.0
    for index in range(bins):
        lower, upper = index / bins, (index + 1) / bins
        members = [i for i, prob in enumerate(p) if lower <= prob < upper or (index == bins - 1 and prob <= upper)]
        if not members:
            continue
        mean_probability = sum(p[i] for i in members) / len(members)
        observed_rate = sum(y[i] for i in members) / len(members)
        ece += (len(members) / len(p)) * abs(mean_probability - observed_rate)
        calibration_bins.append({
            "lower": round(lower, 2), "upper": round(upper, 2), "count": len(members),
            "mean_probability": round(mean_probability, 6), "observed_rate": round(observed_rate, 6),
        })
    return {"brier_score": round(brier, 6), "log_loss": round(log_loss, 6), "ece": round(ece, 6), "calibration_bins": calibration_bins}


def baseline_rank(rows: Sequence[Dict[str, Any]], field: str) -> List[Dict[str, Any]]:
    """Rank a race using one pre-race published ranking as a transparent baseline."""
    def key(row: Dict[str, Any]) -> tuple:
        value = row.get(field)
        try:
            rank = int(value)
        except (TypeError, ValueError):
            rank = 10**6
        return rank, int(row.get("horse_number", 9999))
    return sorted((dict(row) for row in rows), key=key)


def evaluate_race(ranked: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    actual_top3 = {
        int(row["horse_number"])
        for row in ranked
        if int(row.get("top3", 0)) == 1
    }
    actual_winner = next(
        int(row["horse_number"])
        for row in ranked
        if int(row.get("won", 0)) == 1
    )

    predicted_top1 = int(ranked[0]["horse_number"])
    predicted_top3 = {int(row["horse_number"]) for row in ranked[:3]}
    predicted_top5 = {int(row["horse_number"]) for row in ranked[:5]}

    return {
        "winner": actual_winner,
        "predicted_top1": predicted_top1,
        "winner_hit_at_1": predicted_top1 == actual_winner,
        "winner_hit_at_3": actual_winner in predicted_top3,
        "actual_top3": sorted(actual_top3),
        "predicted_top3": sorted(predicted_top3),
        "top3_coverage_by_top3": len(actual_top3 & predicted_top3),
        "top3_coverage_by_top5": len(actual_top3 & predicted_top5),
        "model_ranking": [int(row["horse_number"]) for row in ranked[:5]],
    }


def run_backtest(rows: Sequence[Dict[str, Any]], min_train_races: int = 5) -> Dict[str, Any]:
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row["race_key"])].append(row)

    race_keys = sorted(groups, key=race_sort_key)
    predictions: List[Dict[str, Any]] = []
    calibration_probabilities: List[float] = []
    calibration_labels: List[int] = []

    for index, race_key in enumerate(race_keys):
        if index < min_train_races:
            continue

        train_keys = race_keys[:index]
        train_rows = [row for key in train_keys for row in groups[key]]
        test_rows = groups[race_key]

        try:
            model = fit_top3_model(train_rows)
        except ValueError:
            continue

        probabilities = model.predict_proba(test_rows)
        ranked = rank_rows(test_rows, probabilities)
        evaluation = evaluate_race(ranked)
        baseline_metrics = {}
        for field, name in (("favorites_rank", "favorites"), ("form_rank", "form")):
            baseline = baseline_rank(test_rows, field)
            baseline_eval = evaluate_race(baseline)
            baseline_metrics[name] = {
                "winner_hit_at_1": baseline_eval["winner_hit_at_1"],
                "winner_hit_at_3": baseline_eval["winner_hit_at_3"],
                "top3_coverage_by_top3": baseline_eval["top3_coverage_by_top3"],
                "top3_coverage_by_top5": baseline_eval["top3_coverage_by_top5"],
            }
        evaluation["baselines"] = baseline_metrics
        calibration_probabilities.extend(float(row["predicted_probability"]) for row in ranked)
        # Keep labels aligned with the same horse ordering as the predicted probabilities.
        calibration_labels.extend(int(row.get("top3", 0)) for row in ranked)
        evaluation["race_key"] = race_key
        predictions.append(evaluation)

    evaluated = len(predictions)
    if evaluated == 0:
        raise ValueError("Backtest produced no evaluable races.")

    winner_hit_at_1 = sum(1 for item in predictions if item["winner_hit_at_1"])
    winner_hit_at_3 = sum(1 for item in predictions if item["winner_hit_at_3"])
    coverage3 = sum(item["top3_coverage_by_top3"] for item in predictions)
    coverage5 = sum(item["top3_coverage_by_top5"] for item in predictions)

    baseline_summary = {}
    for name in ("favorites", "form"):
        values = [item["baselines"][name] for item in predictions]
        baseline_summary[name] = {
            "winner_hit_rate_at_1": round(sum(v["winner_hit_at_1"] for v in values) / evaluated, 4),
            "winner_hit_rate_at_3": round(sum(v["winner_hit_at_3"] for v in values) / evaluated, 4),
            "average_actual_top3_covered_by_predicted_top3": round(sum(v["top3_coverage_by_top3"] for v in values) / evaluated, 4),
            "average_actual_top3_covered_by_predicted_top5": round(sum(v["top3_coverage_by_top5"] for v in values) / evaluated, 4),
        }

    calibration = binary_calibration_metrics(calibration_probabilities, calibration_labels)
    report = {
        "method": "walk_forward_logistic_top3",
        "dataset_races": len(race_keys),
        "dataset_rows": len(rows),
        "minimum_training_races": min_train_races,
        "evaluated_races": evaluated,
        "metrics": {
            "winner_hit_rate_at_1": round(winner_hit_at_1 / evaluated, 4),
            "winner_hit_rate_at_3": round(winner_hit_at_3 / evaluated, 4),
            "average_actual_top3_covered_by_predicted_top3": round(coverage3 / evaluated, 4),
            "average_actual_top3_covered_by_predicted_top5": round(coverage5 / evaluated, 4),
            "brier_score_top3": calibration["brier_score"],
            "log_loss_top3": calibration["log_loss"],
            "expected_calibration_error_top3": calibration["ece"],
        },
        "baselines": baseline_summary,
        "calibration": calibration,
        "race_results": predictions,
    }

    return report


def main() -> None:
    rows = load_rows()
    report = run_backtest(rows)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\n" + "=" * 60)
    print("WALK-FORWARD BACKTEST")
    print("=" * 60)
    print(f"Evaluated races: {report['evaluated_races']}")
    for key, value in report["metrics"].items():
        print(f"{key}: {value}")
    print(f"Saved report: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
