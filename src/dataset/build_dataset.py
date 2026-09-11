from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


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


def load_matched_races() -> List[Dict[str, Any]]:
    if not MATCHED_FILE.exists():
        raise FileNotFoundError(
            f"Matched races file not found: {MATCHED_FILE}"
        )

    with MATCHED_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError(
            "matched_races.json must contain a JSON list."
        )

    return data


def get_program_section(record: Dict[str, Any]) -> Dict[str, Any]:
    program = record.get("program")

    if isinstance(program, dict):
        return program

    return record


def get_result_section(record: Dict[str, Any]) -> Dict[str, Any]:
    result = record.get("result")

    if isinstance(result, dict):
        return result

    return {}


def get_race_section(program: Dict[str, Any]) -> Dict[str, Any]:
    race = program.get("race")

    if isinstance(race, dict):
        return race

    return {}


def extract_arrival(result: Dict[str, Any]) -> List[int]:
    arrival = result.get("arrival")

    if not isinstance(arrival, list):
        return []

    clean_arrival = []

    for number in arrival:
        horse_number = safe_int(number)

        if horse_number is not None:
            clean_arrival.append(horse_number)

    return clean_arrival


def build_arrival_map(arrival: List[int]) -> Dict[int, int]:
    return {
        horse_number: position
        for position, horse_number in enumerate(arrival, start=1)
    }


def ranking_position(
    ranking_list: Any,
    horse_number: int,
) -> Optional[int]:
    if not isinstance(ranking_list, list):
        return None

    for position, value in enumerate(ranking_list, start=1):
        number = safe_int(value)

        if number == horse_number:
            return position

    return None


def ranking_score(
    rankings: Dict[str, Any],
    horse_number: int,
) -> Optional[float]:
    positions = []

    for category in (
        "favorites",
        "form",
        "class",
        "progress",
        "regularity",
    ):
        position = ranking_position(
            rankings.get(category),
            horse_number,
        )

        if position is not None:
            positions.append(position)

    if not positions:
        return None

    return round(sum(positions) / len(positions), 4)


def ranking_presence_count(
    rankings: Dict[str, Any],
    horse_number: int,
) -> int:
    count = 0

    for category in (
        "favorites",
        "form",
        "class",
        "progress",
        "regularity",
    ):
        if ranking_position(
            rankings.get(category),
            horse_number,
        ) is not None:
            count += 1

    return count


def build_race_key(
    date: Any,
    track: Any,
    race_number: Any,
) -> Optional[str]:
    normalized_date = normalize_text(date)
    normalized_track = normalize_text(track)
    normalized_race_number = safe_int(race_number)

    if (
        not normalized_date
        or not normalized_track
        or normalized_race_number is None
    ):
        return None

    return (
        f"{normalized_date}|"
        f"{normalized_track}|"
        f"{normalized_race_number}"
    )


def is_verified_match(record: Dict[str, Any]) -> bool:
    match = record.get("match")

    if isinstance(match, dict):
        status = normalize_text(match.get("status"))

        if status:
            return status in {
                "MATCHED",
                "EXACT",
                "VERIFIED",
                "CONFIRMED",
            }

        confidence = safe_float(match.get("confidence"))

        if confidence is not None:
            return confidence >= 100.0

    return (
        isinstance(record.get("program"), dict)
        and isinstance(record.get("result"), dict)
    )


def extract_race_rows(
    record: Dict[str, Any],
) -> Tuple[Optional[str], List[Dict[str, Any]]]:
    if not is_verified_match(record):
        return None, []

    program = get_program_section(record)
    result = get_result_section(record)
    race = get_race_section(program)

    if not result:
        return None, []

    date = (
        program.get("date")
        or record.get("date")
    )

    track = (
        race.get("track")
        or program.get("track")
        or record.get("track")
    )

    race_number = (
        race.get("race_number")
        or program.get("race_number")
        or record.get("race_number")
    )

    race_key = build_race_key(
        date=date,
        track=track,
        race_number=race_number,
    )

    if race_key is None:
        return None, []

    arrival = extract_arrival(result)

    if not arrival:
        return race_key, []

    arrival_map = build_arrival_map(arrival)

    horses = program.get("horses")

    if not isinstance(horses, list):
        horses = []

    rankings = program.get("rankings")

    if not isinstance(rankings, dict):
        rankings = {}

    distance = safe_int(
        race.get("distance")
        or program.get("distance")
    )

    runners_count = safe_int(
        race.get("runners_count")
        or program.get("runners_count")
    )

    prize_euros = safe_float(
        race.get("prize_euros")
        or program.get("prize_euros")
    )

    race_name = (
        race.get("race_name")
        or program.get("race_name")
        or record.get("race_name")
    )

    race_type = (
        race.get("race_type")
        or program.get("race_type")
        or record.get("race_type")
    )

    source_program = (
        record.get("source_program")
        or program.get("source_file")
    )

    source_result = (
        record.get("source_result")
        or result.get("source_file")
    )

    rows: List[Dict[str, Any]] = []

    for horse in horses:
        if not isinstance(horse, dict):
            continue

        horse_number = safe_int(horse.get("number"))

        if horse_number is None:
            continue

        finish_position = arrival_map.get(horse_number)

        # Only horses that have an actual result position are training examples.
        if finish_position is None:
            continue

        favorites_rank = ranking_position(
            rankings.get("favorites"),
            horse_number,
        )

        form_rank = ranking_position(
            rankings.get("form"),
            horse_number,
        )

        class_rank = ranking_position(
            rankings.get("class"),
            horse_number,
        )

        progress_rank = ranking_position(
            rankings.get("progress"),
            horse_number,
        )

        regularity_rank = ranking_position(
            rankings.get("regularity"),
            horse_number,
        )

        avg_ranking = ranking_score(
            rankings,
            horse_number,
        )

        ranking_count = ranking_presence_count(
            rankings,
            horse_number,
        )

        rows.append(
            {
                "race_key": race_key,
                "date": date,
                "track": normalize_text(track),
                "race_number": safe_int(race_number),
                "race_name": race_name,
                "race_type": race_type,
                "distance": distance,
                "runners_count": runners_count,
                "prize_euros": prize_euros,

                "horse_number": horse_number,
                "horse_name": horse.get("horse"),
                "horse_description": horse.get("description"),

                "favorites_rank": favorites_rank,
                "form_rank": form_rank,
                "class_rank": class_rank,
                "progress_rank": progress_rank,
                "regularity_rank": regularity_rank,

                "ranking_average": avg_ranking,
                "ranking_presence": ranking_count,

                "finish_position": finish_position,
                "won": int(finish_position == 1),
                "top3": int(finish_position <= 3),
                "top5": int(finish_position <= 5),
                "placed": int(finish_position <= 6),

                "source_program": source_program,
                "source_result": source_result,
            }
        )

    return race_key, rows


def deduplicate_races(
    records: List[Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    unique: Dict[str, Dict[str, Any]] = {}

    for record in records:
        race_key, _ = extract_race_rows(record)

        if race_key is None:
            continue

        existing = unique.get(race_key)

        if existing is None:
            unique[race_key] = record
            continue

        existing_rows = extract_race_rows(existing)[1]
        current_rows = extract_race_rows(record)[1]

        # Keep the richer record.
        if len(current_rows) > len(existing_rows):
            unique[race_key] = record

    return unique


def build_dataset(
    records: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    unique_races = deduplicate_races(records)

    dataset_rows: List[Dict[str, Any]] = []

    for race_key, record in unique_races.items():
        extracted_key, rows = extract_race_rows(record)

        if extracted_key is None:
            continue

        if not rows:
            continue

        dataset_rows.extend(rows)

    dataset_rows.sort(
        key=lambda row: (
            normalize_text(row.get("date")),
            normalize_text(row.get("track")),
            safe_int(row.get("race_number")) or 0,
            safe_int(row.get("horse_number")) or 0,
        )
    )

    return dataset_rows


def save_json(dataset: List[Dict[str, Any]]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with DATASET_JSON.open("w", encoding="utf-8") as f:
        json.dump(
            dataset,
            f,
            indent=4,
            ensure_ascii=False,
        )


def save_csv(dataset: List[Dict[str, Any]]) -> None:
    import csv

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not dataset:
        return

    fieldnames = list(dataset[0].keys())

    with DATASET_CSV.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            extrasaction="ignore",
        )

        writer.writeheader()

        for row in dataset:
            writer.writerow(row)


def print_summary(
    raw_records: List[Dict[str, Any]],
    dataset: List[Dict[str, Any]],
) -> None:
    races = {
        row["race_key"]
        for row in dataset
        if row.get("race_key")
    }

    wins = sum(
        1
        for row in dataset
        if row.get("won") == 1
    )

    top3 = sum(
        1
        for row in dataset
        if row.get("top3") == 1
    )

    tracks = Counter(
        row.get("track")
        for row in dataset
        if row.get("track")
    )

    print("\n" + "=" * 60)
    print("DATASET BUILD COMPLETE")
    print("=" * 60)

    print(f"Raw matched records: {len(raw_records)}")
    print(f"Unique races: {len(races)}")
    print(f"Training rows: {len(dataset)}")
    print(f"Winners: {wins}")
    print(f"Top-3 rows: {top3}")

    print("\nTracks:")
    for track, count in tracks.most_common():
        print(f"  {track}: {count} horse rows")

    print(f"\nSaved JSON: {DATASET_JSON}")
    print(f"Saved CSV : {DATASET_CSV}")


def main() -> None:
    print("\n" + "=" * 60)
    print("BUILDING HORSE RACING TRAINING DATASET")
    print("=" * 60)

    records = load_matched_races()

    dataset = build_dataset(records)

    if not dataset:
        print("\nNo valid training rows were produced.")
        print(
            "Check data/matched/matched_races.json "
            "and verify that exact matches contain program/result data."
        )
        return

    save_json(dataset)
    save_csv(dataset)

    print_summary(
        raw_records=records,
        dataset=dataset,
    )


if __name__ == "__main__":
    main()
