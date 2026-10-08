import json
from pathlib import Path
from datetime import datetime


BASE_DIR = Path(__file__).resolve().parents[2]

MATCHED_RACES_FILE = BASE_DIR / "data" / "matched" / "matched_races.json"

OUTPUT_DIR = BASE_DIR / "data" / "dataset"

OUTPUT_FILE = OUTPUT_DIR / "training_dataset.json"


def load_json(file_path):
    """
    Safely load a JSON file.
    """

    if not file_path.exists():
        raise FileNotFoundError(
            f"File not found: {file_path}"
        )

    with open(file_path, "r", encoding="utf-8") as file:
        return json.load(file)


def normalize_number(value):
    """
    Convert horse numbers into integers when possible.
    """

    if value is None:
        return None

    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return None


def get_value(data, possible_keys, default=None):
    """
    Try multiple possible field names.

    This makes the dataset builder more tolerant
    of changes in parser field names.
    """

    if not isinstance(data, dict):
        return default

    for key in possible_keys:
        if key in data and data[key] is not None:
            return data[key]

    return default


def extract_arrival(result_data):
    """
    Extract arrival / finishing order from the result object.

    Returns a list of horse numbers.
    """

    possible_keys = [
        "arrival",
        "arrivals",
        "result",
        "results",
        "finish_order",
        "finishing_order",
        "horses",
    ]

    arrival = get_value(result_data, possible_keys, [])

    if arrival is None:
        return []

    extracted = []

    for item in arrival:

        if isinstance(item, dict):

            horse_number = get_value(
                item,
                [
                    "horse_number",
                    "number",
                    "num",
                    "runner_number",
                ]
            )

        else:
            horse_number = item

        horse_number = normalize_number(horse_number)

        if horse_number is not None:
            extracted.append(horse_number)

    return extracted


def get_program_horses(program_data):
    """
    Extract horses from a program race object.
    """

    possible_keys = [
        "horses",
        "runners",
        "entries",
        "participants",
        "starters",
    ]

    horses = get_value(
        program_data,
        possible_keys,
        []
    )

    if horses is None:
        return []

    return horses


def extract_race_metadata(program_data):
    """
    Extract race-level metadata.
    """

    return {
        "date": get_value(
            program_data,
            ["date", "race_date"]
        ),

        "track": get_value(
            program_data,
            [
                "track",
                "hippodrome",
                "racecourse",
                "venue",
            ]
        ),

        "race_number": get_value(
            program_data,
            [
                "race_number",
                "race",
                "course_number",
                "numero_course",
            ]
        ),

        "meeting_number": get_value(
            program_data,
            [
                "meeting_number",
                "reunion_number",
                "meeting",
            ]
        ),

        "race_name": get_value(
            program_data,
            [
                "race_name",
                "name",
                "course_name",
            ]
        ),
    }


def build_horse_row(
    horse,
    race_metadata,
    arrival,
):
    """
    Convert one horse into one training example.
    """

    horse_number = get_value(
        horse,
        [
            "horse_number",
            "number",
            "num",
            "runner_number",
        ]
    )

    horse_number = normalize_number(horse_number)

    horse_name = get_value(
        horse,
        [
            "horse_name",
            "name",
            "horse",
        ]
    )

    row = {
        **race_metadata,

        "horse_number": horse_number,
        "horse_name": horse_name,

        # Program features
        "odds": get_value(
            horse,
            [
                "odds",
                "cote",
                "quote",
            ]
        ),

        "form_rank": get_value(
            horse,
            [
                "form_rank",
                "recent_form_rank",
                "forme_rank",
            ]
        ),

        "class_rank": get_value(
            horse,
            [
                "class_rank",
                "classe_rank",
            ]
        ),

        "favorite_rank": get_value(
            horse,
            [
                "favorite_rank",
                "odds_rank",
                "market_rank",
            ]
        ),

        "progress_rank": get_value(
            horse,
            [
                "progress_rank",
                "improvement_rank",
            ]
        ),

        "regularity_rank": get_value(
            horse,
            [
                "regularity_rank",
                "consistency_rank",
            ]
        ),

        "jockey": get_value(
            horse,
            [
                "jockey",
                "driver",
            ]
        ),

        "trainer": get_value(
            horse,
            [
                "trainer",
                "entraineur",
            ]
        ),

        "driver": get_value(
            horse,
            [
                "driver",
                "jockey",
            ]
        ),

        "owner": get_value(
            horse,
            [
                "owner",
                "proprietaire",
                "proprietaire_nom",
            ]
        ),

        "sex": get_value(
            horse,
            [
                "sex",
                "sexe",
            ]
        ),

        "age": get_value(
            horse,
            [
                "age",
            ]
        ),

        "performance": get_value(
            horse,
            [
                "performance",
                "perf",
                "recent_performance",
            ]
        ),

        "gains": get_value(
            horse,
            [
                "gains",
                "earnings",
            ]
        ),

        "listed_chrono": get_value(
            horse,
            [
                "listed_chrono",
                "chrono",
            ]
        ),

        "listed_distance": get_value(
            horse,
            [
                "listed_distance",
                "distance_listed",
            ]
        ),

        "weight": get_value(
            horse,
            [
                "weight",
                "poids",
            ]
        ),

        "draw": get_value(
            horse,
            [
                "draw",
                "stall",
                "gate",
                "box",
            ]
        ),

        # Target values
        "finished_position": None,
        "finished_top1": 0,
        "finished_top3": 0,
        "finished_top5": 0,
    }

    # Match horse against actual arrival
    if horse_number is not None:

        if horse_number in arrival:

            position = arrival.index(horse_number) + 1

            row["finished_position"] = position

            if position == 1:
                row["finished_top1"] = 1

            if position <= 3:
                row["finished_top3"] = 1

            if position <= 5:
                row["finished_top5"] = 1

    return row


def build_dataset(matched_races):
    """
    Build one row per horse from matched races.
    """

    dataset = []

    processed_races = 0
    skipped_races = 0

    for race in matched_races:

        if not isinstance(race, dict):
            skipped_races += 1
            continue

        program_data = get_value(
            race,
            [
                "program",
                "program_data",
                "race_program",
            ]
        )

        result_data = get_value(
            race,
            [
                "result",
                "result_data",
                "race_result",
            ]
        )

        if not program_data or not result_data:
            skipped_races += 1
            continue

        race_metadata = extract_race_metadata(
            program_data
        )

        horses = get_program_horses(
            program_data
        )

        arrival = extract_arrival(
            result_data
        )

        if not horses:
            skipped_races += 1

            print(
                "Skipping race: "
                f"{race_metadata['date']} | "
                f"{race_metadata['track']} | "
                f"Race {race_metadata['race_number']} "
                "(no horses found)"
            )

            continue

        if not arrival:

            skipped_races += 1

            print(
                "Skipping race: "
                f"{race_metadata['date']} | "
                f"{race_metadata['track']} | "
                f"Race {race_metadata['race_number']} "
                "(no arrival found)"
            )

            continue

        processed_races += 1

        for horse in horses:

            if not isinstance(horse, dict):
                continue

            row = build_horse_row(
                horse=horse,
                race_metadata=race_metadata,
                arrival=arrival,
            )

            dataset.append(row)

    return dataset, processed_races, skipped_races


def validate_dataset(dataset):
    """
    Print basic dataset quality statistics.
    """

    total_rows = len(dataset)

    winners = sum(
        row["finished_top1"]
        for row in dataset
    )

    top3 = sum(
        row["finished_top3"]
        for row in dataset
    )

    top5 = sum(
        row["finished_top5"]
        for row in dataset
    )

    horses_without_numbers = sum(
        1
        for row in dataset
        if row["horse_number"] is None
    )

    horses_without_position = sum(
        1
        for row in dataset
        if row["finished_position"] is None
    )

    print()
    print("=" * 60)
    print("DATASET VALIDATION")
    print("=" * 60)

    print(f"Total horse rows: {total_rows}")
    print(f"Winners: {winners}")
    print(f"Top 3 finishes: {top3}")
    print(f"Top 5 finishes: {top5}")

    print(
        f"Horses without numbers: "
        f"{horses_without_numbers}"
    )

    print(
        f"Horses without finishing position: "
        f"{horses_without_position}"
    )

    if total_rows > 0:

        print(
            f"Winner rate: "
            f"{winners / total_rows:.4f}"
        )

        print(
            f"Top 3 rate: "
            f"{top3 / total_rows:.4f}"
        )

    print("=" * 60)


def save_dataset(dataset):
    """
    Save dataset to JSON.
    """

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    output = {
        "generated_at": datetime.utcnow().isoformat(),
        "total_rows": len(dataset),
        "data": dataset,
    }

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            output,
            file,
            indent=4,
            ensure_ascii=False,
        )

    print()
    print(
        f"Dataset saved to:\n"
        f"{OUTPUT_FILE}"
    )


def main():

    print("=" * 60)
    print("HORSE RACING MACHINE")
    print("DATASET BUILDER")
    print("=" * 60)

    print()
    print(
        f"Loading matched races:\n"
        f"{MATCHED_RACES_FILE}"
    )

    matched_races = load_json(
        MATCHED_RACES_FILE
    )

    # Some files may wrap the races in a key
    if isinstance(matched_races, dict):

        matched_races = get_value(
            matched_races,
            [
                "matched_races",
                "races",
                "data",
            ],
            []
        )

    if not isinstance(matched_races, list):

        raise ValueError(
            "Matched races file does not "
            "contain a list of races."
        )

    print(
        f"Matched races loaded: "
        f"{len(matched_races)}"
    )

    print()
    print("BUILDING DATASET")
    print("-" * 60)

    dataset, processed_races, skipped_races = (
        build_dataset(
            matched_races
        )
    )

    print()
    print(
        f"Processed races: "
        f"{processed_races}"
    )

    print(
        f"Skipped races: "
        f"{skipped_races}"
    )

    print(
        f"Training rows created: "
        f"{len(dataset)}"
    )

    validate_dataset(
        dataset
    )

    save_dataset(
        dataset
    )

    print()
    print("=" * 60)
    print("DATASET BUILD COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
