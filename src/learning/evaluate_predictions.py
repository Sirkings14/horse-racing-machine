from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.live.registry import mark_result_verified
from src.matching.race_matcher import normalize_track
from src.learning.result_truth import build_program_runner_index, validate_arrival

BASE_DIR = Path(__file__).resolve().parents[2]
PREDICTIONS_DIR = BASE_DIR / "data" / "predictions"
RESULTS_DIR = BASE_DIR / "data" / "structured" / "results"
EVALUATION_DIR = BASE_DIR / "data" / "evaluation"
EVALUATION_FILE = EVALUATION_DIR / "prediction_evaluations.json"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_key(value: str) -> str:
    parts = str(value).split("|", 2)
    if len(parts) != 3:
        return str(value)
    try:
        number = int(parts[2])
    except ValueError:
        return str(value)
    return f"{parts[0][:10]}|{normalize_track(parts[1])}|{number}"


def result_records(program_index: dict[str, dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    records: dict[str, dict[str, Any]] = {}
    audit = {"result_races_seen": 0, "accepted": 0, "rejected": 0}
    for path in sorted(RESULTS_DIR.glob("*.json")):
        try:
            payload = load_json(path)
        except Exception as error:
            print(f"Skipping unreadable result {path.name}: {error}")
            continue
        if not isinstance(payload, dict) or payload.get("document_type") != "result":
            continue
        race_date = str(payload.get("date") or "")[:10]
        track = normalize_track(payload.get("track"))
        for race in payload.get("races") or []:
            audit["result_races_seen"] += 1
            try:
                number = int(race.get("race_number"))
            except (TypeError, ValueError):
                continue
            if not race_date or not track:
                continue
            key = f"{race_date}|{track}|{number}"
            arrival = []
            for value in race.get("arrival") or []:
                try:
                    arrival.append(int(value))
                except (TypeError, ValueError):
                    pass
            truth = validate_arrival(key, arrival, program_index)
            if not truth["accepted_for_learning"]:
                audit["rejected"] += 1
                print(f"Skipping untrusted result {key}: {truth['reason']}")
                continue
            audit["accepted"] += 1
            records[key] = {
                "race_key": key, "date": race_date, "track": track, "race_number": number,
                "arrival": arrival, "winner": arrival[0],
                "second": arrival[1], "third": arrival[2],
                "truth_validation": truth,
            }
    return records, audit


def load_existing(program_index: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if not EVALUATION_FILE.exists():
        return {}
    try:
        payload = load_json(EVALUATION_FILE)
    except Exception:
        return {}
    if not isinstance(payload, list):
        return {}

    cleaned: dict[str, dict[str, Any]] = {}
    quarantined = 0
    for item in payload:
        if not isinstance(item, dict) or not item.get("race_key"):
            continue
        key = canonical_key(str(item.get("race_key")))
        arrival = []
        for value in ((item.get("result") or {}).get("arrival") or []):
            try:
                arrival.append(int(value))
            except (TypeError, ValueError):
                pass
        truth = validate_arrival(key, arrival, program_index)
        if not truth["accepted_for_learning"]:
            quarantined += 1
            continue
        cleaned[key] = item

    if quarantined:
        print(f"Quarantined {quarantined} previously stored evaluation(s) failing result-truth validation.")
    return cleaned


def _engine_metrics(predicted: list[int], actual_top3: list[int], actual_top5: list[int]) -> dict[str, Any]:
    top3 = predicted[:3]
    top5 = predicted[:5]
    return {
        "winner_hit": bool(predicted) and predicted[0] == actual_top5[0],
        "winner_in_top3": actual_top5[0] in top3,
        "winner_in_top5": actual_top5[0] in top5,
        "actual_top3_covered_by_top3": len(set(actual_top3) & set(top3)),
        "actual_top3_covered_by_top5": len(set(actual_top3) & set(top5)),
        "actual_top5_covered_by_top5": len(set(actual_top5) & set(top5)),
        "exact_top3_order": top3 == actual_top3,
        "exact_top5_order": top5 == actual_top5,
        "top5_position_hits": sum(
            1 for position, horse in enumerate(top5)
            if position < len(actual_top5) and horse == actual_top5[position]
        ),
    }


def evaluate(prediction: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    actual_top3 = result["arrival"][:3]
    actual_top5 = result["arrival"][:5]
    predicted_top3 = [int(x) for x in prediction.get("top3_numbers") or []]
    predicted_recommended = [int(x) for x in prediction.get("recommended_numbers") or []]
    predicted_order = [int(x) for x in prediction.get("predicted_finish_order") or []]
    order_top5 = [int(x) for x in prediction.get("order_engine_top5") or []]
    ranked_top5 = [
        int(x.get("horse_number"))
        for x in (prediction.get("ranked_horses") or [])[:5]
        if x.get("horse_number") is not None
    ]
    fused_top5 = predicted_order[:5] if predicted_order else predicted_top3[:5]
    predicted_winner = predicted_order[0] if predicted_order else (predicted_top3[0] if predicted_top3 else None)

    strength_metrics = _engine_metrics(ranked_top5, actual_top3, actual_top5)
    order_metrics = _engine_metrics(order_top5, actual_top3, actual_top5)
    fused_metrics = _engine_metrics(fused_top5, actual_top3, actual_top5)

    return {
        "race_key": prediction.get("race_key"),
        "prediction_id": prediction.get("prediction_id"),
        "model_version": prediction.get("model_version", "unknown"),
        "predicted_at": prediction.get("generated_at"),
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "result": result,
        "prediction": {
            "recommended_numbers": predicted_recommended,
            "top3_numbers": predicted_top3,
            "ranked_top5": ranked_top5,
            "predicted_finish_order_top5": predicted_order[:5],
            "order_engine_top5": order_top5[:5],
            "monitoring": prediction.get("monitoring") or {},
            "difficulty": prediction.get("difficulty") or {},
        },
        "metrics": {
            "winner_hit": predicted_winner == result.get("winner"),
            "winner_in_top3": result.get("winner") in predicted_top3,
            "winner_in_top5": result.get("winner") in ranked_top5,
            "order_engine_winner_hit": order_metrics["winner_hit"],
            "strength_engine_winner_hit": strength_metrics["winner_hit"],
            "fused_engine_winner_hit": fused_metrics["winner_hit"],
            "actual_top3_covered_by_predicted_top3": len(set(actual_top3) & set(predicted_top3)),
            "actual_top3_covered_by_predicted_top5": len(set(actual_top3) & set(ranked_top5)),
            "recommended_hit_count": len(set(predicted_recommended) & set(result["arrival"])),
            "exact_top3_order": fused_metrics["exact_top3_order"],
            "exact_top5_order": fused_metrics["exact_top5_order"],
            "top5_position_hits": fused_metrics["top5_position_hits"],
            "engine_attribution": {
                "strength": strength_metrics,
                "order": order_metrics,
                "fused": fused_metrics,
            },
        },
        "status": "result_verified",
        "result_validation": result.get("truth_validation") or {
            "accepted_for_learning": True,
            "minimum_positions_required": 3,
            "arrival_positions_available": len(result["arrival"]),
        },
    }


def safe_prediction_files() -> list[Path]:
    return sorted(PREDICTIONS_DIR.glob("*.json")) if PREDICTIONS_DIR.exists() else []


def main() -> dict[str, Any]:
    program_index = build_program_runner_index()
    results, truth_audit = result_records(program_index)
    evaluations = load_existing(program_index)
    processed = 0

    for path in safe_prediction_files():
        try:
            prediction = load_json(path)
        except Exception as error:
            print(f"Skipping unreadable prediction {path.name}: {error}")
            continue
        if not isinstance(prediction, dict) or prediction.get("mode") != "live_registry_prediction":
            continue
        original_key = prediction.get("race_key")
        if not original_key:
            continue
        key = canonical_key(str(original_key))
        if key in evaluations:
            continue
        result = results.get(key)
        if not result:
            continue
        evaluations[key] = evaluate(prediction, result)
        mark_result_verified(str(original_key), str(EVALUATION_FILE.relative_to(BASE_DIR)))
        processed += 1

    EVALUATION_DIR.mkdir(parents=True, exist_ok=True)
    truth_audit["stored_evaluations_quarantined"] = 0
    ordered = [evaluations[key] for key in sorted(evaluations)]
    audit_path = EVALUATION_DIR / "result_truth_audit.json"
    audit_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                **truth_audit,
                "stored_verified_evaluations_after_quarantine": len(ordered),
                "policy": {
                    "unknown_result_numbers_never_train": True,
                    "duplicate_arrival_numbers_never_train": True,
                    "fewer_than_three_positions_never_train": True,
                    "program_roster_is_authoritative": True,
                },
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    EVALUATION_FILE.write_text(json.dumps(ordered, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Verified prediction/result pairs added: {processed}")
    print(f"Total verified prediction/result pairs: {len(ordered)}")
    print(
        "Result truth audit: "
        f"{truth_audit['accepted']} accepted / "
        f"{truth_audit['rejected']} rejected."
    )
    return {"processed": processed, "total": len(ordered), "path": str(EVALUATION_FILE)}


if __name__ == "__main__":
    main()
