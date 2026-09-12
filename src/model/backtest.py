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
        evaluation["race_key"] = race_key
        predictions.append(evaluation)

    evaluated = len(predictions)
    if evaluated == 0:
        raise ValueError("Backtest produced no evaluable races.")

    winner_hit_at_1 = sum(1 for item in predictions if item["winner_hit_at_1"])
    winner_hit_at_3 = sum(1 for item in predictions if item["winner_hit_at_3"])
    coverage3 = sum(item["top3_coverage_by_top3"] for item in predictions)
    coverage5 = sum(item["top3_coverage_by_top5"] for item in predictions)

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
        },
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
