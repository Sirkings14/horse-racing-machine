import json
import hashlib
from pathlib import Path


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parents[2]

PROGRAMS_DIR = BASE_DIR / "data" / "structured" / "programs"
RESULTS_DIR = BASE_DIR / "data" / "structured" / "results"
DATASET_DIR = BASE_DIR / "data" / "dataset"

OUTPUT_FILE = DATASET_DIR / "horse_racing_dataset.json"


# ============================================================
# FILE HELPERS
# ============================================================

def load_json_files(folder):
    """
    Load every JSON file from a folder.
    """

    records = []

    for file_path in folder.glob("*.json"):
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                data = json.load(file)

            records.append(
                {
                    "file_path": file_path,
                    "data": data
                }
            )

        except Exception as error:
            print(f"Failed to load {file_path.name}: {error}")

    return records


def create_content_hash(data):
    """
    Create a stable hash from JSON content.

    This helps us detect duplicate files containing
    the same race data.
    """

    normalized = json.dumps(
        data,
        sort_keys=True,
        ensure_ascii=False
    )

    return hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()


# ============================================================
# DEDUPLICATION
# ============================================================

def deduplicate_records(records, record_type):
    """
    Remove duplicate records based on content.
    """

    unique_records = []
    seen_hashes = set()

    duplicates = 0

    for record in records:

        data = record["data"]

        content_hash = create_content_hash(data)

        if content_hash in seen_hashes:
            duplicates += 1

            print(
                f"Duplicate {record_type} skipped: "
                f"{record['file_path'].name}"
            )

            continue

        seen_hashes.add(content_hash)

        unique_records.append(record)

    print()

    print(
        f"Unique {record_type}: {len(unique_records)}"
    )

    print(
        f"Duplicate {record_type}: {duplicates}"
    )

    return unique_records


# ============================================================
# RANK HELPERS
# ============================================================

def get_rank(rankings, ranking_name, horse_number):
    """
    Return the ranking position of a horse.

    Example:

    favorites = [14, 11, 5]

    Horse 14 -> rank 1
    Horse 11 -> rank 2
    Horse 5  -> rank 3

    If the horse is not present,
    return None.
    """

    ranking = rankings.get(
        ranking_name,
        []
    )

    if horse_number not in ranking:
        return None

    return ranking.index(horse_number) + 1


# ============================================================
# RESULT HELPERS
# ============================================================

def normalize_results(result_data):
    """
    Convert result data into a consistent structure.

    Expected output:

    {
        race_number: {
            horse_number: finishing_position
        }
    }
    """

    races = result_data.get("races", {})

    normalized = {}

    # --------------------------------------------------------
    # FORMAT 1
    #
    # "races": {
    #     "1": [1, 8, 5],
    #     "2": [2, 4, 6]
    # }
    # --------------------------------------------------------

    if isinstance(races, dict):

        for race_number, arrival in races.items():

            if not isinstance(arrival, list):
                continue

            positions = {}

            for position, horse_number in enumerate(
                arrival,
                start=1
            ):

                if not isinstance(horse_number, int):
                    continue

                positions[horse_number] = position

            normalized[str(race_number)] = positions

    # --------------------------------------------------------
    # FORMAT 2
    #
    # "races": [
    #     {
    #         "race_number": 1,
    #         "arrival": [3, 9, 8]
    #     }
    # ]
    # --------------------------------------------------------

    elif isinstance(races, list):

        for race in races:

            if not isinstance(race, dict):
                continue

            race_number = race.get(
                "race_number"
            )

            arrival = race.get(
                "arrival",
                []
            )

            if race_number is None:
                continue

            if not isinstance(arrival, list):
                continue

            positions = {}

            for position, horse_number in enumerate(
                arrival,
                start=1
            ):

                if not isinstance(horse_number, int):
                    continue

                positions[horse_number] = position

            normalized[str(race_number)] = positions

    return normalized


# ============================================================
# PROGRAM / RESULT MATCHING
# ============================================================

def find_matching_result(
    program_data,
    result_records
):
    """
    Try to find a result file matching the program.

    Matching is currently based on:

    - Date
    - Track
    - Race number

    Important:
    Program dates and result dates may not always
    match because a result file may contain multiple
    races or a different meeting structure.

    Therefore this first version uses a conservative
    matching strategy.
    """

    program_date = program_data.get(
        "date"
    )

    program_track = (
        program_data
        .get("race", {})
        .get("track")
    )

    program_race_number = (
        program_data
        .get("race", {})
        .get("race_number")
    )

    matches = []

    for result_record in result_records:

        result_data = result_record["data"]

        result_date = result_data.get(
            "date"
        )

        result_track = result_data.get(
            "track"
        )

        if (
            program_date == result_date
            and
            program_track == result_track
        ):

            normalized_races = normalize_results(
                result_data
            )

            race_key = str(
                program_race_number
            )

            if race_key in normalized_races:

                matches.append(
                    {
                        "result_file": (
                            result_record[
                                "file_path"
                            ].name
                        ),
                        "positions": (
                            normalized_races[
                                race_key
                            ]
                        )
                    }
                )

    if not matches:
        return None

    return matches[0]


# ============================================================
# DATASET RECORD BUILDER
# ============================================================

def build_horse_record(
    program_data,
    horse,
    result_match
):
    """
    Build one machine-learning-ready record
    for one horse.
    """

    race = program_data.get(
        "race",
        {}
    )

    rankings = program_data.get(
        "rankings",
        {}
    )

    horse_number = horse.get(
        "number"
    )

    finished_position = None

    if result_match is not None:

        finished_position = (
            result_match[
                "positions"
            ].get(
                horse_number
            )
        )

    record = {

        # ----------------------------------------------------
        # RACE INFORMATION
        # ----------------------------------------------------

        "date": program_data.get(
            "date"
        ),

        "track": race.get(
            "track"
        ),

        "race_name": race.get(
            "race_name"
        ),

        "race_number": race.get(
            "race_number"
        ),

        "race_type": race.get(
            "race_type"
        ),

        "runners_count": race.get(
            "runners_count"
        ),

        "distance": race.get(
            "distance"
        ),

        "prize_euros": race.get(
            "prize_euros"
        ),

        # ----------------------------------------------------
        # HORSE INFORMATION
        # ----------------------------------------------------

        "horse_number": horse_number,

        "horse": horse.get(
            "horse"
        ),

        "description": horse.get(
            "description"
        ),

        # ----------------------------------------------------
        # RANKING FEATURES
        # ----------------------------------------------------

        "favorite_rank": get_rank(
            rankings,
            "favorites",
            horse_number
        ),

        "form_rank": get_rank(
            rankings,
            "form",
            horse_number
        ),

        "class_rank": get_rank(
            rankings,
            "class",
            horse_number
        ),

        "progress_rank": get_rank(
            rankings,
            "progress",
            horse_number
        ),

        "regularity_rank": get_rank(
            rankings,
            "regularity",
            horse_number
        ),

        # ----------------------------------------------------
        # RESULTS
        # ----------------------------------------------------

        "finished_position": (
            finished_position
        ),

        "winner": (
            finished_position == 1
            if finished_position is not None
            else None
        ),

        "top_3": (
            finished_position is not None
            and finished_position <= 3
        ),

        "top_5": (
            finished_position is not None
            and finished_position <= 5
        ),

        # ----------------------------------------------------
        # SOURCE INFORMATION
        # ----------------------------------------------------

        "source_program": (
            program_data.get(
                "source_file"
            )
        ),

        "source_result": (
            result_match[
                "result_file"
            ]
            if result_match
            else None
        )
    }

    return record


# ============================================================
# BUILD DATASET
# ============================================================

def build_dataset():

    print()

    print("=" * 60)

    print("BUILDING HORSE RACING DATASET")

    print("=" * 60)

    print()

    # --------------------------------------------------------
    # CREATE OUTPUT FOLDER
    # --------------------------------------------------------

    DATASET_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    # --------------------------------------------------------
    # LOAD PROGRAMS
    # --------------------------------------------------------

    print(
        "Loading program data..."
    )

    program_records = load_json_files(
        PROGRAMS_DIR
    )

    print(
        f"Program files loaded: "
        f"{len(program_records)}"
    )

    # --------------------------------------------------------
    # LOAD RESULTS
    # --------------------------------------------------------

    print(
        "Loading result data..."
    )

    result_records = load_json_files(
        RESULTS_DIR
    )

    print(
        f"Result files loaded: "
        f"{len(result_records)}"
    )

    print()

    # --------------------------------------------------------
    # DEDUPLICATE
    # --------------------------------------------------------

    print(
        "Checking for duplicate programs..."
    )

    unique_programs = deduplicate_records(
        program_records,
        "programs"
    )

    print()

    print(
        "Checking for duplicate results..."
    )

    unique_results = deduplicate_records(
        result_records,
        "results"
    )

    # --------------------------------------------------------
    # BUILD RECORDS
    # --------------------------------------------------------

    dataset = []

    matched_programs = 0

    unmatched_programs = 0

    for program_record in unique_programs:

        program_data = (
            program_record["data"]
        )

        horses = program_data.get(
            "horses",
            []
        )

        if not horses:

            print(
                "Skipping program with no horses: "
                f"{program_record['file_path'].name}"
            )

            continue

        # ----------------------------------------------------
        # FIND RESULT
        # ----------------------------------------------------

        result_match = find_matching_result(
            program_data,
            unique_results
        )

        if result_match:

            matched_programs += 1

            print(
                "MATCHED: "
                f"{program_record['file_path'].name}"
            )

            print(
                f"  Result: "
                f"{result_match['result_file']}"
            )

        else:

            unmatched_programs += 1

            print(
                "UNMATCHED: "
                f"{program_record['file_path'].name}"
            )

        # ----------------------------------------------------
        # BUILD HORSE RECORDS
        # ----------------------------------------------------

        for horse in horses:

            record = build_horse_record(
                program_data,
                horse,
                result_match
            )

            dataset.append(
                record
            )

    # --------------------------------------------------------
    # SAVE DATASET
    # --------------------------------------------------------

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            dataset,
            file,
            ensure_ascii=False,
            indent=4
        )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    print()

    print("=" * 60)

    print(
        "DATASET BUILD COMPLETE"
    )

    print("=" * 60)

    print()

    print(
        f"Programs processed: "
        f"{len(unique_programs)}"
    )

    print(
        f"Programs matched to results: "
        f"{matched_programs}"
    )

    print(
        f"Programs without results: "
        f"{unmatched_programs}"
    )

    print(
        f"Total horse records: "
        f"{len(dataset)}"
    )

    print()

    print(
        "Dataset saved to:"
    )

    print(
        OUTPUT_FILE
    )

    print()

    return dataset


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    build_dataset()
