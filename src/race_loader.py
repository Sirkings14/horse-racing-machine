import json

from pathlib import Path

from src.data_validation import (
    canonicalize_race,
    dataset_health,
    extract_races,
    validate_race,
)


def load_races(
    folder,
    source_type,
):
    """
    Load, extract, canonicalize,
    and validate races.

    Invalid races are separated
    from valid races.
    """

    folder = Path(
        folder
    )

    valid_races = []

    invalid_races = []

    files_processed = 0

    raw_records = 0

    for path in folder.glob(
        "*.json"
    ):

        files_processed += 1

        try:

            with open(
                path,
                "r",
                encoding="utf-8",
            ) as file:

                data = json.load(
                    file
                )

        except Exception as error:

            print(

                f"FAILED LOADING "
                f"{path.name}: "
                f"{error}"

            )

            continue

        extracted = extract_races(
            data
        )

        raw_records += len(
            extracted
        )

        for record in extracted:

            race = canonicalize_race(

                record,

                source_type=
                    source_type,

                source_file=
                    path.name,

            )

            validation = validate_race(
                race
            )

            if validation[
                "valid"
            ]:

                valid_races.append(
                    race
                )

            else:

                invalid_races.append({

                    "race":
                        race,

                    "errors":
                        validation[
                            "errors"
                        ],

                })

    health = dataset_health(
        valid_races
    )

    return {

        "source_type":
            source_type,

        "files_processed":
            files_processed,

        "raw_records":
            raw_records,

        "valid_races":
            valid_races,

        "invalid_races":
            invalid_races,

        "health":
            health,

    }
