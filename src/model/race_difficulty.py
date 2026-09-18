from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[2]
EVALUATION_FILE = BASE_DIR / "data" / "evaluation" / "prediction_evaluations.json"
OUTPUT_FILE = BASE_DIR / "data" / "model" / "race_difficulty_report.json"


def classify_race(ranked_horses: list[dict[str, Any]], order_ranking: list[dict[str, Any]], runners_count: int | None = None) -> dict[str, Any]:
    if not ranked_horses:
        return {"bucket": "unknown", "difficulty_score": None, "signals": ["no_ranked_horses"]}

    field_size = runners_count or len(ranked_horses)
    top = [float(x.get("probability_top3", 0.0)) for x in ranked_horses[:3]]
    top1 = top[0] if top else 0.0
    top2 = top[1] if len(top) > 1 else 0.0
    top3 = top[2] if len(top) > 2 else 0.0
    margin = max(0.0, top1 - top2)
    spread = max(0.0, top1 - top3)

    strength = {int(x["horse_number"]) for x in ranked_horses[:5] if x.get("horse_number") is not None}
    order = {int(x["horse_number"]) for x in order_ranking[:5] if x.get("horse_number") is not None}
    overlap = len(strength & order) / max(1, min(5, len(strength)))

    score = 20.0
    score += min(25.0, max(0.0, (0.06 - margin) / 0.06 * 25.0))
    score += min(20.0, max(0.0, (0.12 - spread) / 0.12 * 20.0))
    score += min(20.0, max(0.0, (field_size - 10) * 2.0))
    score += (1.0 - overlap) * 15.0
    score = round(min(100.0, max(0.0, score)), 2)

    bucket = "low" if score < 40 else "medium" if score < 65 else "high"
    signals = []
    if margin < 0.02: signals.append("tight_top1_top2_margin")
    if spread < 0.05: signals.append("tight_top1_top3_spread")
    if field_size >= 15: signals.append("large_field")
    if overlap < 0.6: signals.append("engine_disagreement")
    if not order_ranking: signals.append("order_engine_unavailable")

    return {
        "bucket": bucket,
        "difficulty_score": score,
        "field_size": field_size,
        "top1_top2_margin": round(margin, 6),
        "top1_top3_spread": round(spread, 6),
        "engine_top5_overlap": round(overlap, 4),
        "signals": signals,
    }


def build_difficulty_report(evaluations: list[dict[str, Any]]) -> dict[str, Any]:
    groups = {"low": [], "medium": [], "high": []}
    for item in evaluations:
        bucket = ((item.get("prediction") or {}).get("difficulty") or {}).get("bucket")
        if bucket in groups: groups[bucket].append(item)

    buckets = {}
    for bucket, items in groups.items():
        metrics = [x.get("metrics") or {} for x in items]
        n = len(items)
        buckets[bucket] = {"verified_races": n}
        if n:
            buckets[bucket].update({
                "winner_hit_rate": round(mean(bool(m.get("winner_hit")) for m in metrics), 4),
                "winner_in_top3_rate": round(mean(bool(m.get("winner_in_top3")) for m in metrics), 4),
                "exact_top3_order_rate": round(mean(bool(m.get("exact_top3_order")) for m in metrics), 4),
                "exact_top5_order_rate": round(mean(bool(m.get("exact_top5_order")) for m in metrics), 4),
                "average_recommended_hit_count": round(mean(float(m.get("recommended_hit_count", 0)) for m in metrics), 3),
            })

    return {
        "method": "transparent_pre_race_difficulty_classifier",
        "higher_score_means_more_difficult": True,
        "bucket_thresholds": {"low": "<40", "medium": "40-64.99", "high": ">=65"},
        "total_verified_predictions": len(evaluations),
        "buckets": buckets,
    }


def main():
    try:
        payload = json.loads(EVALUATION_FILE.read_text(encoding="utf-8"))
        evaluations = payload if isinstance(payload, list) else []
    except (OSError, json.JSONDecodeError):
        evaluations = []
    report = build_difficulty_report(evaluations)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("RACE DIFFICULTY REPORT")
    print(f"Verified predictions: {report['total_verified_predictions']}")
    return report


if __name__ == "__main__":
    main()
