from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.model.feature_engineering import row_to_features
from src.model.logistic_model import LogisticModel


BASE_DIR = Path(__file__).resolve().parents[2]
PROGRAM_DIR = BASE_DIR / "data" / "structured" / "programs"
DATASET_FILE = BASE_DIR / "data" / "dataset" / "training_dataset_clean.json"
MODEL_FILE = BASE_DIR / "data" / "model" / "top3_model.json"
OUTPUT_FILE = BASE_DIR / "data" / "model" / "latest_prediction.json"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def race_key(program: Dict[str, Any]) -> Optional[str]:
    race = program.get("race") or {}
    date = program.get("date")
    track = race.get("track") or program.get("track")
    number = race.get("race_number")
    if not date or not track or number is None:
        return None
    return f"{str(date).strip()}|{str(track).strip().upper()}|{int(number)}"


def program_sort_key(item: Tuple[Path, Dict[str, Any]]) -> Tuple[str, str, int]:
    path, program = item
    race = program.get("race") or {}
    return (
        str(program.get("date") or ""),
        str(race.get("track") or ""),
        int(race.get("race_number") or 0),
    )


def rankings_to_positions(rankings: Dict[str, Any]) -> Dict[str, Dict[int, int]]:
    output: Dict[str, Dict[int, int]] = {}
    for name in ("favorites", "form", "class", "progress", "regularity"):
        values = rankings.get(name)
        positions: Dict[int, int] = {}
        if isinstance(values, list):
            for position, value in enumerate(values, start=1):
                try:
                    positions[int(value)] = position
                except (TypeError, ValueError):
                    continue
        output[name] = positions
    return output


def program_to_rows(program: Dict[str, Any]) -> List[Dict[str, Any]]:
    race = program.get("race") or {}
    rankings = rankings_to_positions(program.get("rankings") or {})
    horses = program.get("horses") or []

    rows: List[Dict[str, Any]] = []
    for horse in horses:
        if not isinstance(horse, dict):
            continue
        try:
            number = int(horse.get("number"))
        except (TypeError, ValueError):
            continue
        if number <= 0:
            continue

        values = {
            "distance": race.get("distance"),
            "runners_count": race.get("runners_count"),
            "favorites_rank": rankings["favorites"].get(number),
            "form_rank": rankings["form"].get(number),
            "class_rank": rankings["class"].get(number),
            "progress_rank": rankings["progress"].get(number),
            "regularity_rank": rankings["regularity"].get(number),
        }
        present = sum(value is not None for value in values.values())
        rank_values = [
            value for key, value in values.items()
            if key.endswith("_rank") and value is not None
        ]

        row = {
            "race_key": race_key(program),
            "date": program.get("date"),
            "track": race.get("track"),
            "race_number": race.get("race_number"),
            "race_name": race.get("race_name"),
            "race_type": race.get("race_type"),
            "distance": race.get("distance"),
            "runners_count": race.get("runners_count"),
            "horse_number": number,
            "horse_name": horse.get("horse"),
            "horse_description": horse.get("description"),
            "favorites_rank": values["favorites_rank"],
            "form_rank": values["form_rank"],
            "class_rank": values["class_rank"],
            "progress_rank": values["progress_rank"],
            "regularity_rank": values["regularity_rank"],
            "ranking_average": (sum(rank_values) / len(rank_values)) if rank_values else None,
            "ranking_presence": present - 2 if present >= 2 else present,
        }
        rows.append(row)

    return rows


def load_historical_races() -> set[str]:
    data = load_json(DATASET_FILE)
    if not isinstance(data, list):
        return set()
    return {
        str(row.get("race_key"))
        for row in data
        if row.get("race_key")
    }


def load_programs() -> List[Tuple[Path, Dict[str, Any]]]:
    programs: List[Tuple[Path, Dict[str, Any]]] = []
    for path in sorted(PROGRAM_DIR.glob("*.json")):
        try:
            payload = load_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and payload.get("race") and payload.get("horses"):
            programs.append((path, payload))
    return programs


def main() -> None:
    model = LogisticModel.from_dict(load_json(MODEL_FILE))
    historical = load_historical_races()
    programs = sorted(load_programs(), key=program_sort_key, reverse=True)

    selected: Optional[Tuple[Path, Dict[str, Any]]] = None
    prediction_mode = "future_or_unmatched"

    for item in programs:
        key = race_key(item[1])
        if key and key not in historical:
            selected = item
            break

    if selected is None:
        if not programs:
            raise ValueError("No structured program files are available for prediction.")
        selected = programs[0]
        prediction_mode = "retrospective_latest_available"

    path, program = selected
    rows = program_to_rows(program)
    probabilities = model.predict_proba(rows)

    ranked = []
    for row, probability in zip(rows, probabilities):
        ranked.append({
            "horse_number": int(row["horse_number"]),
            "horse_name": row.get("horse_name"),
            "probability_top3": round(float(probability), 6),
            "ranking_average": row.get("ranking_average"),
            "ranking_presence": row.get("ranking_presence"),
        })

    ranked.sort(key=lambda item: (-item["probability_top3"], item["horse_number"]))
    for position, item in enumerate(ranked, start=1):
        item["predicted_rank"] = position

    result = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "mode": prediction_mode,
        "source_program": path.name,
        "race_key": race_key(program),
        "race": program.get("race"),
        "recommended_numbers": [item["horse_number"] for item in ranked[:5]],
        "top3_numbers": [item["horse_number"] for item in ranked[:3]],
        "ranked_horses": ranked,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\n" + "=" * 60)
    print("LATEST RACE PREDICTION")
    print("=" * 60)
    print(f"Mode: {prediction_mode}")
    print(f"Race: {result['race_key']}")
    print(f"Five-number recommendation: {result['recommended_numbers']}")
    print(f"Top-3 recommendation: {result['top3_numbers']}")
    print(f"Saved prediction: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
