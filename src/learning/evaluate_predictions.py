from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[2]
PREDICTIONS_DIR = BASE_DIR / "data" / "predictions"
RESULTS_DIR = BASE_DIR / "data" / "structured" / "results"
EVALUATION_DIR = BASE_DIR / "data" / "evaluation"
EVALUATION_FILE = EVALUATION_DIR / "prediction_evaluations.json"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def result_records() -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for path in sorted(RESULTS_DIR.glob("*.json")):
        try:
            payload = load_json(path)
        except Exception as error:
            print(f"Skipping unreadable result {path.name}: {error}")
            continue
        if not isinstance(payload, dict) or payload.get("document_type") != "result":
            continue

        date = str(payload.get("date") or "")[:10]
        track = str(payload.get("track") or "").strip().upper()
        for race in payload.get("races") or []:
            try:
                number = int(race.get("race_number"))
            except (TypeError, ValueError):
                continue
            if not date or not track:
                continue
            key = f"{date}|{track}|{number}"
            arrival = []
            for value in race.get("arrival") or []:
                try:
                    arrival.append(int(value))
                except (TypeError, ValueError):
                    pass
            if not arrival:
                continue
            records[key] = {
                "race_key": key,
                "date": date,
                "track": track,
                "race_number": number,
                "arrival": arrival,
                "winner": arrival[0],
                "second": arrival[1] if len(arrival) > 1 else None,
                "third": arrival[2] if len(arrival) > 2 else None,
            }
    return records


def load_existing() -> dict[str, dict[str, Any]]:
    if not EVALUATION_FILE.exists():
        return {}
    try:
        payload = load_json(EVALUATION_FILE)
    except Exception:
        return {}
    if not isinstance(payload, list):
        return {}
    return {str(item.get("race_key")): item for item in payload if isinstance(item, dict) and item.get("race_key")}


def evaluate(prediction: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    actual = set(result["arrival"])
    predicted_top3 = [int(x) for x in prediction.get("top3_numbers") or []]
    predicted_recommended = [int(x) for x in prediction.get("recommended_numbers") or []]
    top5 = [int(x.get("horse_number")) for x in (prediction.get("ranked_horses") or [])[:5] if x.get("horse_number") is not None]
    predicted_winner = int(predicted_top3[0]) if predicted_top3 else None

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
            "ranked_top5": top5,
        },
        "metrics": {
            "winner_hit": predicted_winner == result.get("winner"),
            "winner_in_top3": result.get("winner") in predicted_top3,
            "winner_in_top5": result.get("winner") in top5,
            "actual_top3_covered_by_predicted_top3": len(set(predicted_top3) & actual),
            "actual_top3_covered_by_predicted_top5": len(set(top5) & actual),
            "recommended_hit_count": len(set(predicted_recommended) & actual),
        },
        "status": "result_verified",
    }


def safe_prediction_files() -> list[Path]:
    return sorted(PREDICTIONS_DIR.glob("*.json")) if PREDICTIONS_DIR.exists() else []


def main() -> dict[str, Any]:
    results = result_records()
    evaluations = load_existing()
    processed = 0

    for path in safe_prediction_files():
        try:
            prediction = load_json(path)
        except Exception as error:
            print(f"Skipping unreadable prediction {path.name}: {error}")
            continue
        if not isinstance(prediction, dict) or prediction.get("mode") != "live_registry_prediction":
            continue
        key = prediction.get("race_key")
        if not key or key in evaluations:
            continue
        result = results.get(str(key))
        if not result:
            continue
        evaluations[str(key)] = evaluate(prediction, result)
        processed += 1

    EVALUATION_DIR.mkdir(parents=True, exist_ok=True)
    ordered = [evaluations[key] for key in sorted(evaluations)]
    EVALUATION_FILE.write_text(json.dumps(ordered, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Verified prediction/result pairs added: {processed}")
    print(f"Total verified prediction/result pairs: {len(ordered)}")
    return {"processed": processed, "total": len(ordered), "path": str(EVALUATION_FILE)}


if __name__ == "__main__":
    main()
