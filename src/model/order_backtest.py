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


def score_predictions(predicted_order, actual_order):
    pair_correct = pair_total = 0
    for i in range(len(actual_order)):
        for j in range(i + 1, len(actual_order)):
            pair_total += 1
            pair_correct += int(predicted_order.index(actual_order[i]) < predicted_order.index(actual_order[j]))
    top_n = min(5, len(actual_order), len(predicted_order))
    position_hits = sum(predicted_order[i] == actual_order[i] for i in range(top_n))
    return pair_correct, pair_total, position_hits, top_n, predicted_order[:3] == actual_order[:3], predicted_order[:5] == actual_order[:5]


def main() -> Dict[str, Any]:
    rows = load_rows()
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("race_key") and row.get("finish_position") is not None:
            groups[str(row["race_key"])].append(row)

    race_keys = sorted(groups, key=race_sort_key)
    if len(race_keys) < 20:
        report = {
            "method": "walk_forward_pairwise_finishing_order",
            "status": "insufficient_data",
            "reason": "fewer_than_20_verified_races",
            "dataset_races": len(race_keys),
            "warmup_races": None,
            "evaluated_races": 0,
            "metrics": None,
            "baseline": {"pairwise_random_accuracy": 0.5},
            "per_race": [],
        }
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_FILE.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Order backtest skipped honestly: only {len(race_keys)} verified races are available; 20 are required.")
        print(f"Saved report: {OUTPUT_FILE}")
        return report

    warmup = max(10, int(len(race_keys) * 0.5))
    totals = {"pair_correct": 0, "pair_total": 0, "position_hits": 0, "position_total": 0, "exact_top3": 0, "exact_top5": 0}
    evaluated = 0
    per_race = []

    for index in range(warmup, len(race_keys)):
        train_keys = race_keys[:index]
        test_key = race_keys[index]
        train_rows = [row for key in train_keys for row in groups[key]]
        test_rows = groups[test_key]
        model = fit_order_model(train_rows)
        predicted = model.predict_order(test_rows)
        predicted_order = [item["horse_number"] for item in predicted]
        actual_order = [int(row["horse_number"]) for row in sorted(test_rows, key=lambda r: int(r["finish_position"]))]
        pc, pt, ph, ptotal, e3, e5 = score_predictions(predicted_order, actual_order)
        totals["pair_correct"] += pc
        totals["pair_total"] += pt
        totals["position_hits"] += ph
        totals["position_total"] += ptotal
        totals["exact_top3"] += int(e3)
        totals["exact_top5"] += int(e5)
        evaluated += 1
        per_race.append({
            "race_key": test_key,
            "pairwise_accuracy": round(pc / pt, 4) if pt else None,
            "top5_position_accuracy": round(ph / ptotal, 4) if ptotal else None,
            "exact_top3": e3,
            "exact_top5": e5,
        })

    metrics = {
        "pairwise_order_accuracy": round(totals["pair_correct"] / totals["pair_total"], 4),
        "top5_position_accuracy": round(totals["position_hits"] / totals["position_total"], 4),
        "exact_top3_order_rate": round(totals["exact_top3"] / evaluated, 4),
        "exact_top5_order_rate": round(totals["exact_top5"] / evaluated, 4),
    }
    report = {
        "method": "walk_forward_pairwise_finishing_order",
        "dataset_races": len(race_keys),
        "warmup_races": warmup,
        "evaluated_races": evaluated,
        "metrics": metrics,
        "baseline": {"pairwise_random_accuracy": 0.5},
        "per_race": per_race[-100:],
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n" + "=" * 60)
    print("FINISHING-ORDER WALK-FORWARD BACKTEST")
    print("=" * 60)
    print(f"Evaluated races: {evaluated}")
    for key, value in metrics.items():
        print(f"{key}: {value}")
    print(f"Saved report: {OUTPUT_FILE}")
    return report


if __name__ == "__main__":
    main()
