from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

from src.model.order_model import fit_order_model

BASE_DIR = Path(__file__).resolve().parents[2]
DATASET_FILE = BASE_DIR / "data" / "dataset" / "training_dataset_clean.json"
OUTPUT_FILE = BASE_DIR / "data" / "model" / "order_backtest_report.json"


def race_sort_key(race_key: str) -> tuple:
    date, track, race_number = race_key.split("|", 2)
    return date, track, int(race_number)


def load_rows() -> List[Dict[str, Any]]:
    rows = json.loads(DATASET_FILE.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("Clean training dataset must be a JSON list.")
    return rows


def main() -> Dict[str, Any]:
    rows = load_rows()
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("race_key") and row.get("finish_position") is not None:
            groups[str(row["race_key"])].append(row)

    race_keys = sorted(groups, key=race_sort_key)
    if len(race_keys) < 20:
        raise ValueError("Order backtest needs at least 20 verified races.")

    split = max(10, int(len(race_keys) * 0.8))
    train_keys = race_keys[:split]
    test_keys = race_keys[split:]
    train_rows = [row for key in train_keys for row in groups[key]]
    model = fit_order_model(train_rows)

    pair_correct = 0
    pair_total = 0
    position_hits = 0
    position_total = 0
    exact_top3 = 0
    exact_top5 = 0
    evaluated = 0

    for race_key in test_keys:
        test_rows = groups[race_key]
        predicted = model.predict_order(test_rows)
        predicted_order = [item["horse_number"] for item in predicted]
        actual_order = [int(row["horse_number"]) for row in sorted(test_rows, key=lambda r: int(r["finish_position"]))]

        for i in range(len(actual_order)):
            for j in range(i + 1, len(actual_order)):
                pair_total += 1
                pair_correct += int(predicted_order.index(actual_order[i]) < predicted_order.index(actual_order[j]))

        top_n = min(5, len(actual_order), len(predicted_order))
        position_hits += sum(predicted_order[i] == actual_order[i] for i in range(top_n))
        position_total += top_n
        exact_top3 += int(predicted_order[:3] == actual_order[:3])
        exact_top5 += int(predicted_order[:5] == actual_order[:5])
        evaluated += 1

    report = {
        "method": "time_holdout_pairwise_finishing_order",
        "dataset_races": len(race_keys),
        "training_races": len(train_keys),
        "holdout_races": len(test_keys),
        "metrics": {
            "pairwise_order_accuracy": round(pair_correct / pair_total, 4) if pair_total else None,
            "top5_position_accuracy": round(position_hits / position_total, 4) if position_total else None,
            "exact_top3_order_rate": round(exact_top3 / evaluated, 4) if evaluated else None,
            "exact_top5_order_rate": round(exact_top5 / evaluated, 4) if evaluated else None,
        },
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n" + "=" * 60)
    print("FINISHING-ORDER HOLDOUT BACKTEST")
    print("=" * 60)
    print(f"Holdout races: {report['holdout_races']}")
    for key, value in report["metrics"].items():
        print(f"{key}: {value}")
    print(f"Saved report: {OUTPUT_FILE}")
    return report


if __name__ == "__main__":
    main()
