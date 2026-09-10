import json
from pathlib import Path


# --------------------------------------------------
# PATHS
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parents[2]

MATCHED_DIR = BASE_DIR / "data" / "matched"
DATASET_DIR = BASE_DIR / "data" / "dataset"

MATCHED_FILE = MATCHED_DIR / "matched_races.json"
OUTPUT_FILE = DATASET_DIR / "horse_training_dataset.json"


# --------------------------------------------------
# HELPERS
# --------------------------------------------------

def get_rank(horse_number, ranking_list):
    """
    Return the ranking position of a horse.

    Example:
    ranking_list = [13, 16, 14]

    Horse 13 -> rank 1
    Horse 16 -> rank 2
    Horse 14 -> rank 3

    If horse is not found, return None.
    """

    if not ranking_list:
        return None

    try:
        return ranking_list.index(horse_number) + 1

    except ValueError:
        return None


def create_rank_features(horse_number, rankings):
    """
    Create ranking-based features for one horse.
    """

    return {

        "favorite_rank": get_rank(
            horse_number,
            rankings.get("favorites", [])
        ),

        "form_rank": get_rank(
            horse_number,
            rankings.get("form", [])
        ),

        "class_rank": get_rank(
            horse_number,
            rankings.get("class", [])
        ),

        "progress_rank": get_rank(
            horse_number,
            rankings.get("progress", [])
        ),

        "regularity_rank": get_rank(
            horse_number,
            rankings.get("regularity", [])
        ),

    }


def create_binary_features(horse_number, rankings):
    """
    Create simple yes/no ranking features.
    """

    favorites = rankings.get("favorites", [])
    form = rankings.get("form", [])
    class_rankings = rankings.get("class", [])
    progress = rankings.get("progress", [])
    regularity = rankings.get("regularity", [])

    return {

        "is_favorite": int(
            horse_number in favorites
        ),

        "is_form_ranked": int(
            horse_number in form
        ),

        "is_class_ranked": int(
            horse_number in class_rankings
        ),

        "is_progress_ranked": int(
            horse_number in progress
        ),

        "is_regularity_ranked": int(
            horse_number in regularity
        ),

    }


def create_result_features(
    horse_number,
    actual_arrival
):
    """
    Create target labels from the real result.
    """

    if not actual_arrival:
        return {

            "actual_position": None,

            "won": 0,

            "top_3": 0,

            "top_5": 0,

        }

    try:

        position = (
            actual_arrival.index(
                horse_number
            )
            + 1
        )

    except ValueError:

        position = None

    return {

        "actual_position": position,

        "won": int(
            position == 1
        ),

        "top_3": int(
            position is not None
            and position <= 3
        ),

        "top_5": int(
            position is not None
            and position <= 5
        ),

    }


# --------------------------------------------------
# LOAD MATCHED RACES
# --------------------------------------------------

def load_matched_races():
    """
    Load matched race data.
    """

    if not MATCHED_FILE.exists():

        print(
            f"Matched file not found:\n"
            f"{MATCHED_FILE}"
        )

        return []

    try:

        with open(
            MATCHED_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

    except Exception as error:

        print(
            f"Error loading matched races: "
            f"{error}"
        )

        return []

    # Support the current matcher output format
    if isinstance(data, dict):

        return data.get(
            "matched_races",
            []
        )

    # Also support a plain list
    if isinstance(data, list):

        return data

    return []


# --------------------------------------------------
# BUILD DATASET
# --------------------------------------------------

def build_dataset(
    matched_races
):

    print("\n" + "=" * 60)
    print("BUILDING HORSE TRAINING DATASET")
    print("=" * 60)

    dataset_rows = []

    for race in matched_races:

        date = race.get("date")

        track = race.get("track")

        race_number = race.get(
            "race_number"
        )

        race_name = race.get(
            "race_name"
        )

        race_type = race.get(
            "race_type"
        )

        distance = race.get(
            "distance"
        )

        runners_count = race.get(
            "runners_count"
        )

        horses = race.get(
            "horses",
            []
        )

        rankings = race.get(
            "rankings",
            {}
        )

        actual_arrival = race.get(
            "actual_arrival",
            []
        )

        print(
            f"\nProcessing: "
            f"{date} | "
            f"{track} | "
            f"Race {race_number}"
        )

        for horse in horses:

            horse_number = horse.get(
                "number"
            )

            horse_name = horse.get(
                "horse"
            )

            description = horse.get(
                "description"
            )

            # ------------------------------------------
            # RANK FEATURES
            # ------------------------------------------

            rank_features = (
                create_rank_features(
                    horse_number,
                    rankings
                )
            )

            # ------------------------------------------
            # BINARY FEATURES
            # ------------------------------------------

            binary_features = (
                create_binary_features(
                    horse_number,
                    rankings
                )
            )

            # ------------------------------------------
            # RESULT / TARGET FEATURES
            # ------------------------------------------

            result_features = (
                create_result_features(
                    horse_number,
                    actual_arrival
                )
            )

            # ------------------------------------------
            # CREATE DATASET ROW
            # ------------------------------------------

            row = {

                # --------------------------------------
                # RACE INFORMATION
                # --------------------------------------

                "date": date,

                "track": track,

                "race_number": race_number,

                "race_name": race_name,

                "race_type": race_type,

                "distance": distance,

                "runners_count": runners_count,

                # --------------------------------------
                # HORSE INFORMATION
                # --------------------------------------

                "horse_number": horse_number,

                "horse_name": horse_name,

                "description": description,

                # --------------------------------------
                # RANK FEATURES
                # --------------------------------------

                **rank_features,

                # --------------------------------------
                # BINARY FEATURES
                # --------------------------------------

                **binary_features,

                # --------------------------------------
                # RESULT LABELS
                # --------------------------------------

                **result_features,

            }

            dataset_rows.append(
                row
            )

    return dataset_rows


# --------------------------------------------------
# SAVE DATASET
# --------------------------------------------------

def save_dataset(
    dataset_rows
):

    DATASET_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    output = {

        "dataset": dataset_rows,

        "summary": {

            "total_rows": len(
                dataset_rows
            ),

            "total_races": len(
                set(
                    (
                        row.get("date"),
                        row.get("track"),
                        row.get("race_number")
                    )

                    for row
                    in dataset_rows
                )
            ),

            "total_winners": sum(

                row.get(
                    "won",
                    0
                )

                for row
                in dataset_rows

            ),

            "total_top_3": sum(

                row.get(
                    "top_3",
                    0
                )

                for row
                in dataset_rows

            ),

        }

    }

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            output,
            file,
            indent=4,
            ensure_ascii=False
        )

    print("\n" + "=" * 60)
    print("DATASET BUILD COMPLETE")
    print("=" * 60)

    print(
        f"\nDataset rows: "
        f"{len(dataset_rows)}"
    )

    print(
        f"Output saved:\n"
        f"{OUTPUT_FILE}"
    )


# --------------------------------------------------
# MAIN
# --------------------------------------------------

def run_dataset_builder():

    print("\n" + "=" * 60)
    print("HORSE RACING MACHINE")
    print("DATASET BUILDER")
    print("=" * 60)

    matched_races = (
        load_matched_races()
    )

    print(
        f"\nMatched races loaded: "
        f"{len(matched_races)}"
    )

    if not matched_races:

        print(
            "\nNo matched races found."
        )

        return []

    dataset_rows = (
        build_dataset(
            matched_races
        )
    )

    save_dataset(
        dataset_rows
    )

    return dataset_rows


# --------------------------------------------------
# RUN DIRECTLY
# --------------------------------------------------

if __name__ == "__main__":

    run_dataset_builder()
