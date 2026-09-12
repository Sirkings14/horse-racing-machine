from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


BASE_DIR = Path(__file__).resolve().parents[2]

MATCHED_FILE = (
    BASE_DIR
    / "data"
    / "matched"
    / "matched_races.json"
)

OUTPUT_DIR = (
    BASE_DIR
    / "data"
    / "dataset"
)

DATASET_JSON = (
    OUTPUT_DIR
    / "training_dataset.json"
)

DATASET_CSV = (
    OUTPUT_DIR
    / "training_dataset.csv"
)


def normalize_text(value: Any) -> str:
    if value is None:
        return ""

    return " ".join(
        str(value)
        .strip()
        .upper()
        .split()
    )


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
    Return True when the program identifies a horse
    as a non-runner / withdrawn horse.
    """

    horse_name = normalize_text(
        horse.get("horse")
    )

    description = normalize_text(
        horse.get("description")
    )

    non_runner_markers = (
        "NON PARTANT",
        "NON-PARTANT",
        "NON PARTANTE",
        "NON-PARTANTE",
        "NP",
    )

    for marker in non_runner_markers:
        if marker in horse_name:
            return True

        if marker in description:
            return True

    return False


def load_matched_races() -> List[Dict[str, Any]]:
    if not MATCHED_FILE.exists():
        raise FileNotFoundError(
            f"Matched races file not found: "
            f"{MATCHED_FILE}"
        )

    with MATCHED_FILE.open(
        "r",
        encoding="utf-8",
    ) as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError(
            "matched_races.json must contain "
            "a JSON list."
        )

    return data


def get_program_section(
    record: Dict[str, Any]
) -> Dict[str, Any]:

    program = record.get("program")

    if isinstance(program, dict):
        return program

    return record


def get_result_section(
    record: Dict[str, Any]
) -> Dict[str, Any]:

    result = record.get("result")

    if isinstance(result, dict):
        return result

    return {}


def get_race_section(
    program: Dict[str, Any]
) -> Dict[str, Any]:

    race = program.get("race")

    if isinstance(race, dict):
        return race

    return {}


def is_verified_match(
    record: Dict[str, Any]
) -> bool:

    match = record.get("match")

    if isinstance(match, dict):

        status = normalize_text(
            match.get("status")
        )

        if status:
            return status in {
                "MATCHED",
                "EXACT",
                "VERIFIED",
                "CONFIRMED",
            }

        confidence = safe_float(
            match.get("confidence")
        )

        if confidence is not None:
            return confidence >= 100.0

    return (
        isinstance(
            record.get("program"),
            dict,
        )
        and isinstance(
            record.get("result"),
            dict,
        )
    )


def extract_arrival(
    result: Dict[str, Any]
) -> List[int]:

    arrival = result.get(
        "arrival"
    )

    if not isinstance(
        arrival,
        list,
    ):
        return []

    output = []

    for value in arrival:

        number = safe_int(
            value
        )

        if number is not None:
            output.append(number)

    return output


def build_arrival_map(
    arrival: List[int]
) -> Dict[int, int]:

    return {
        horse_number: position
        for position, horse_number
        in enumerate(
            arrival,
            start=1,
        )
    }


def ranking_position(
    ranking_list: Any,
    horse_number: int,
) -> Optional[int]:

    if not isinstance(
        ranking_list,
        list,
    ):
        return None

    for position, value in enumerate(
        ranking_list,
        start=1,
    ):

        if safe_int(value) == horse_number:
            return position

    return None


def ranking_average(
    rankings: Dict[str, Any],
    horse_number: int,
) -> Optional[float]:

    positions = []

    categories = (
        "favorites",
        "form",
        "class",
        "progress",
        "regularity",
    )

    for category in categories:

        position = ranking_position(
            rankings.get(category),
            horse_number,
        )

        if position is not None:
            positions.append(position)

    if not positions:
        return None

    return round(
        sum(positions)
        / len(positions),
        4,
    )


def ranking_presence(
    rankings: Dict[str, Any],
    horse_number: int,
) -> int:

    count = 0

    categories = (
        "favorites",
        "form",
        "class",
        "progress",
        "regularity",
    )

    for category in categories:

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

    normalized_date = normalize_text(
        date
    )

    normalized_track = normalize_text(
        track
    )

    number = safe_int(
        race_number
    )

    if not normalized_date:
        return None

    if not normalized_track:
        return None

    if number is None:
        return None

    return (
        f"{normalized_date}|"
        f"{normalized_track}|"
        f"{number}"
    )


def extract_race_rows(
    record: Dict[str, Any],
) -> Tuple[
    Optional[str],
    List[Dict[str, Any]],
    int,
]:

    if not is_verified_match(
        record
    ):
        return None, [], 0

    program = get_program_section(
        record
    )

    result = get_result_section(
        record
    )

    race = get_race_section(
        program
    )

    if not result:
        return None, [], 0

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
        return None, [], 0

    horses = program.get(
        "horses"
    )

    if not isinstance(
        horses,
        list,
    ):
        horses = []

    if not horses:
        return race_key, [], 0

    arrival = extract_arrival(
        result
    )

    arrival_map = build_arrival_map(
        arrival
    )

    rankings = program.get(
        "rankings"
    )

    if not isinstance(
        rankings,
        dict,
    ):
        rankings = {}

    race_distance = safe_int(
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

    rows: List[
        Dict[str, Any]
    ] = []

    excluded_non_runners = 0

    seen_horse_numbers = set()

    for horse in horses:

        if not isinstance(
            horse,
            dict,
        ):
            continue

        if is_non_runner(
            horse
        ):
            excluded_non_runners += 1
            continue

        horse_number = safe_int(
            horse.get("number")
        )

        if horse_number is None:
            continue

        # Protect the dataset from duplicate horse
        # numbers even if an older parsed JSON still
        # contains duplicates.
        if horse_number in seen_horse_numbers:
            continue

        seen_horse_numbers.add(
            horse_number
        )

        finish_position = (
            arrival_map.get(
                horse_number
            )
        )

        if finish_position is not None:

            won = int(
                finish_position == 1
            )

            top3 = int(
                finish_position <= 3
            )

        else:

            won = 0
            top3 = 0

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

        avg_rank = ranking_average(
            rankings,
            horse_number,
        )

        presence = ranking_presence(
            rankings,
            horse_number,
        )

        rows.append(
            {
                "race_key": race_key,
                "date": date,
                "track": normalize_text(
                    track
                ),
                "race_number": safe_int(
                    race_number
                ),
                "race_name": race_name,
                "race_type": race_type,
                "distance": race_distance,
                "runners_count": (
                    runners_count
                ),
                "prize_euros": (
                    prize_euros
                ),

                "horse_number": (
                    horse_number
                ),
                "horse_name": (
                    horse.get("horse")
                ),
                "horse_description": (
                    horse.get("description")
                ),

                "favorites_rank": (
                    favorites_rank
                ),
                "form_rank": (
                    form_rank
                ),
                "class_rank": (
                    class_rank
                ),
                "progress_rank": (
                    progress_rank
                ),
                "regularity_rank": (
                    regularity_rank
                ),

                "ranking_average": (
                    avg_rank
                ),
                "ranking_presence": (
                    presence
                ),

                "finish_position": (
                    finish_position
                ),
                "won": won,
                "top3": top3,

                "source_program": (
                    source_program
                ),
                "source_result": (
                    source_result
                ),
            }
        )

    return (
        race_key,
        rows,
        excluded_non_runners,
    )


def deduplicate_records(
    records: List[Dict[str, Any]],
) -> Dict[
    str,
    Dict[str, Any],
]:

    unique = {}

    for record in records:

        race_key, rows, _ = (
            extract_race_rows(
                record
            )
        )

        if race_key is None:
            continue

        if not rows:
            continue

        existing = unique.get(
            race_key
        )

        if existing is None:

            unique[race_key] = record
            continue

        (
            _,
            existing_rows,
            _,
        ) = extract_race_rows(
            existing
        )

        if len(rows) > len(
            existing_rows
        ):
            unique[race_key] = record

    return unique


def build_dataset(
    records: List[Dict[str, Any]],
) -> Tuple[
    List[Dict[str, Any]],
    int,
]:

    unique_records = (
        deduplicate_records(
            records
        )
    )

    dataset = []

    excluded_non_runners = 0

    for record in (
        unique_records.values()
    ):

        (
            _,
            rows,
            excluded,
        ) = extract_race_rows(
            record
        )

        excluded_non_runners += (
            excluded
        )

        if not rows:
            continue

        dataset.extend(
            rows
        )

    dataset.sort(
        key=lambda row: (
            normalize_text(
                row.get("date")
            ),
            normalize_text(
                row.get("track")
            ),
            safe_int(
                row.get("race_number")
            ) or 0,
            safe_int(
                row.get("horse_number")
            ) or 0,
        )
    )

    return (
        dataset,
        excluded_non_runners,
    )


def save_json(
    dataset: List[Dict[str, Any]]
) -> None:

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    with DATASET_JSON.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            dataset,
            file,
            indent=4,
            ensure_ascii=False,
        )


def save_csv(
    dataset: List[Dict[str, Any]]
) -> None:

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not dataset:
        return

    fieldnames = list(
        dataset[0].keys()
    )

    with DATASET_CSV.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
            extrasaction="ignore",
        )

        writer.writeheader()

        writer.writerows(
            dataset
        )


def print_summary(
    raw_records: List[Dict[str, Any]],
    dataset: List[Dict[str, Any]],
    excluded_non_runners: int,
) -> None:

    race_keys = {
        row["race_key"]
        for row in dataset
        if row.get("race_key")
    }

    winners = sum(
        row.get("won", 0)
        for row in dataset
    )

    top3 = sum(
        row.get("top3", 0)
        for row in dataset
    )

    tracks = Counter(
        row.get("track")
        for row in dataset
        if row.get("track")
    )

    print(
        "\n"
        + "=" * 60
    )

    print(
        "DATASET BUILD COMPLETE"
    )

    print(
        "=" * 60
    )

    print(
        f"Raw matched records: "
        f"{len(raw_records)}"
    )

    print(
        f"Unique races: "
        f"{len(race_keys)}"
    )

    print(
        f"Training rows: "
        f"{len(dataset)}"
    )

    print(
        f"Winners: "
        f"{winners}"
    )

    print(
        f"Top-3 rows: "
        f"{top3}"
    )

    print(
        f"Non-runners excluded: "
        f"{excluded_non_runners}"
    )

    print(
        "\nRows per race:"
    )

    for race_key in sorted(
        race_keys
    ):

        count = sum(
            1
            for row in dataset
            if row.get(
                "race_key"
            ) == race_key
        )

        print(
            f"  {race_key}: "
            f"{count}"
        )

    print(
        "\nTracks:"
    )

    for track, count in (
        tracks.most_common()
    ):

        print(
            f"  {track}: "
            f"{count} horse rows"
        )

    print(
        f"\nSaved JSON: "
        f"{DATASET_JSON}"
    )

    print(
        f"Saved CSV : "
        f"{DATASET_CSV}"
    )


def main() -> None:

    print(
        "\n"
        + "=" * 60
    )

    print(
        "BUILDING HORSE RACING "
        "TRAINING DATASET"
    )

    print(
        "=" * 60
    )

    records = load_matched_races()

    (
        dataset,
        excluded_non_runners,
    ) = build_dataset(
        records
    )

    if not dataset:

        print(
            "\nNo valid training rows "
            "were produced."
        )

        return

    save_json(
        dataset
    )

    save_csv(
        dataset
    )

    print_summary(
        raw_records=records,
        dataset=dataset,
        excluded_non_runners=(
            excluded_non_runners
        ),
    )


if __name__ == "__main__":
    main()
