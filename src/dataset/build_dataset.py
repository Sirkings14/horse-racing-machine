from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional


BASE_DIR = Path(__file__).resolve().parents[2]

MATCHED_FILE = BASE_DIR / "data" / "matched" / "matched_races.json"
OUTPUT_DIR = BASE_DIR / "data" / "dataset"
DATASET_JSON = OUTPUT_DIR / "training_dataset.json"
DATASET_CSV = OUTPUT_DIR / "training_dataset.csv"


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().upper().split())


def safe_int(value: Any) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def safe_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def is_non_runner(horse: Dict[str, Any]) -> bool:
    """
    Detect a real non-runner without interpreting historical result text
    appended to a horse description as a withdrawal marker.
    """

    horse_name = normalize_text(horse.get("horse"))
    description = normalize_text(horse.get("description"))

    # Strong markers in the horse-name field.
    if horse_name in {"NP", "NON PARTANT", "NON-PARTANT", "NON PARTANTE", "NON-PARTANTE"}:
        return True

    # Explicit non-runner wording in the horse name.
    if re.search(r"\bNON[\s-]+PARTANT(?:E)?\b", horse_name):
        return True

    # Only treat a description as a non-runner declaration when the
    # declaration is at the beginning/end of the field. This avoids
    # matching appended historical result blocks such as `... NP : 8`.
    if re.search(r"^(?:NP|NON[\s-]+PARTANT(?:E)?)\b", description):
        return True

    return False


def load_matched_races() -> List[Dict[str, Any]]:
    if not MATCHED_FILE.exists():
        raise FileNotFoundError(f"Matched races file not found: {MATCHED_FILE}")

    with MATCHED_FILE.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError("matched_races.json must contain a JSON list.")

    return data


def get_program_section(record: Dict[str, Any]) -> Dict[str, Any]:
    program = record.get("program")
    return program if isinstance(program, dict) else record


def get_result_section(record: Dict[str, Any]) -> Dict[str, Any]:
    result = record.get("result")
    return result if isinstance(result, dict) else {}


def get_race_section(program: Dict[str, Any]) -> Dict[str, Any]:
    race = program.get("race")
    return race if isinstance(race, dict) else {}


def is_verified_match(record: Dict[str, Any]) -> bool:
    match = record.get("match")

    if isinstance(match, dict):
        status = normalize_text(match.get("status"))
        if status:
            return status in {"MATCHED", "EXACT", "VERIFIED", "CONFIRMED"}

        confidence = safe_float(match.get("confidence"))
        if confidence is not None:
            return confidence >= 100.0

    return (
        isinstance(record.get("program"), dict)
        and isinstance(record.get("result"), dict)
    )


def extract_arrival(result: Dict[str, Any]) -> List[int]:
    arrival = result.get("arrival")

    if not isinstance(arrival, list):
        return []

    output: List[int] = []

    for value in arrival:
        number = safe_int(value)
        if number is not None and number > 0:
            output.append(number)

    return output


def build_arrival_map(arrival: List[int]) -> Dict[int, int]:
    return {
        horse_number: position
        for position, horse_number in enumerate(arrival, start=1)
    }


def ranking_position(ranking_list: Any, horse_number: int) -> Optional[int]:
    if not isinstance(ranking_list, list):
        return None

    for position, value in enumerate(ranking_list, start=1):
        if safe_int(value) == horse_number:
            return position

    return None


def extract_rankings(program: Dict[str, Any]) -> Dict[str, Any]:
    rankings = program.get("rankings")
    return rankings if isinstance(rankings, dict) else {}


def extract_horses(program: Dict[str, Any]) -> List[Dict[str, Any]]:
    horses = program.get("horses")
    if not isinstance(horses, list):
        return []
    return [horse for horse in horses if isinstance(horse, dict)]


def build_race_key(date: Any, track: Any, race_number: Any) -> Optional[str]:
    normalized_date = normalize_text(date)
    normalized_track = normalize_text(track)
    normalized_race_number = safe_int(race_number)

    if not normalized_date or not normalized_track or normalized_race_number is None:
        return None

    return f"{normalized_date}|{normalized_track}|{normalized_race_number}"


def extract_race_rows(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not is_verified_match(record):
        return []

    program = get_program_section(record)
    result = get_result_section(record)
    race = get_race_section(program)

    date = program.get("date") or result.get("date")
    track = race.get("track") or program.get("track") or result.get("track")
    race_number = race.get("race_number") or result.get("race_number")

    race_key = build_race_key(date, track, race_number)
    if race_key is None:
        return []

    arrival = extract_arrival(result)
    arrival_map = build_arrival_map(arrival)
    rankings = extract_rankings(program)
    horses = extract_horses(program)

    if not arrival_map or not horses:
        return []

    rows: List[Dict[str, Any]] = []
    seen_numbers = set()

    for horse in horses:
        if is_non_runner(horse):
            continue

        horse_number = safe_int(horse.get("number"))
        if horse_number is None or horse_number <= 0:
            continue

        if horse_number in seen_numbers:
            continue

        seen_numbers.add(horse_number)

        finish_position = arrival_map.get(horse_number)
        top3 = 1 if finish_position is not None and finish_position <= 3 else 0
        won = 1 if finish_position == 1 else 0

        ranking_values = {
            "favorites_rank": ranking_position(rankings.get("favorites"), horse_number),
            "form_rank": ranking_position(rankings.get("form"), horse_number),
            "class_rank": ranking_position(rankings.get("class"), horse_number),
            "progress_rank": ranking_position(rankings.get("progress"), horse_number),
            "regularity_rank": ranking_position(rankings.get("regularity"), horse_number),
        }

        ranking_numbers = [value for value in ranking_values.values() if value is not None]
        ranking_average = round(sum(ranking_numbers) / len(ranking_numbers), 4) if ranking_numbers else None

        rows.append(
            {
                "race_key": race_key,
                "date": date,
                "track": track,
                "race_number": safe_int(race_number),
                "race_name": race.get("race_name"),
                "race_type": race.get("race_type"),
                "distance": safe_int(race.get("distance")),
                "runners_count": safe_int(race.get("runners_count")),
                "prize_euros": safe_float(race.get("prize_euros")),
                "horse_number": horse_number,
                "horse_name": horse.get("horse"),
                "horse_description": horse.get("description"),
                **ranking_values,
                "ranking_average": ranking_average,
                "ranking_presence": len(ranking_numbers),
                "finish_position": finish_position,
                "won": won,
                "top3": top3,
                "source_program": program.get("source_file"),
                "source_result": result.get("source_file"),
            }
        )

    return rows


def deduplicate_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}

    for record in records:
        program = get_program_section(record)
        race = get_race_section(program)
        result = get_result_section(record)

        race_key = build_race_key(
            program.get("date") or result.get("date"),
            race.get("track") or program.get("track") or result.get("track"),
            race.get("race_number") or result.get("race_number"),
        )

        if race_key is None:
            continue

        grouped.setdefault(race_key, []).append(record)

    output: List[Dict[str, Any]] = []

    for records_for_race in grouped.values():
        best = max(
            records_for_race,
            key=lambda record: len(extract_horses(get_program_section(record))),
        )
        output.append(best)

    return output


def write_json(rows: List[Dict[str, Any]]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with DATASET_JSON.open("w", encoding="utf-8") as file:
        json.dump(rows, file, indent=4, ensure_ascii=False)


def write_csv(rows: List[Dict[str, Any]]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "race_key", "date", "track", "race_number", "race_name", "race_type",
        "distance", "runners_count", "prize_euros", "horse_number", "horse_name",
        "horse_description", "favorites_rank", "form_rank", "class_rank",
        "progress_rank", "regularity_rank", "ranking_average", "ranking_presence",
        "finish_position", "won", "top3", "source_program", "source_result",
    ]

    with DATASET_CSV.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    print("\n" + "=" * 60)
    print("BUILDING HORSE RACING TRAINING DATASET")
    print("=" * 60)

    matched_records = load_matched_races()
    unique_records = deduplicate_records(matched_records)

    all_rows: List[Dict[str, Any]] = []
    non_runner_count = 0

    for record in unique_records:
        before = len(extract_horses(get_program_section(record)))
        rows = extract_race_rows(record)
        after = len(rows)
        non_runner_count += max(before - after, 0)
        all_rows.extend(rows)

    write_json(all_rows)
    write_csv(all_rows)

    race_counter = Counter(row["race_key"] for row in all_rows)
    winner_count = sum(1 for row in all_rows if row["won"] == 1)
    top3_count = sum(1 for row in all_rows if row["top3"] == 1)

    print("=" * 60)
    print("DATASET BUILD COMPLETE")
    print("=" * 60)
    print(f"Raw matched records: {len(matched_records)}")
    print(f"Unique races: {len(race_counter)}")
    print(f"Training rows: {len(all_rows)}")
    print(f"Winners: {winner_count}")
    print(f"Top-3 rows: {top3_count}")
    print(f"Non-runners excluded: {non_runner_count}")
    print("Rows per race:")
    for race_key, count in sorted(race_counter.items()):
        print(f"  {race_key}: {count}")

    track_counter = Counter(row["track"] for row in all_rows)
    print("Tracks:")
    for track, count in track_counter.most_common():
        print(f"  {track}: {count} horse rows")

    print(f"Saved JSON: {DATASET_JSON}")
    print(f"Saved CSV : {DATASET_CSV}")


if __name__ == "__main__":
    main()
