import json
from pathlib import Path


def count_records(folder_path):
    """
    Count usable JSON records inside a folder.
    """

    folder = Path(folder_path)

    if not folder.exists():
        return 0, []

    total_records = 0
    files_checked = []

    for path in folder.glob("*.json"):

        try:

            with open(
                path,
                "r",
                encoding="utf-8",
            ) as file:

                data = json.load(file)

            if isinstance(data, list):

                total_records += len(data)

            elif isinstance(data, dict):

                total_records += 1

            files_checked.append(path.name)

        except Exception as error:

            print(
                f"VALIDATION ERROR: "
                f"{path.name}: {error}"
            )

    return total_records, files_checked


def validate_pipeline_data():

    print("\n" + "=" * 60)
    print("PIPELINE DATA VALIDATION")
    print("=" * 60)

    program_count, program_files = count_records(
        "data/structured/programs"
    )

    result_count, result_files = count_records(
        "data/structured/results"
    )

    print(
        f"\nStructured program records: "
        f"{program_count}"
    )

    print(
        f"Program JSON files: "
        f"{len(program_files)}"
    )

    print(
        f"\nStructured result records: "
        f"{result_count}"
    )

    print(
        f"Result JSON files: "
        f"{len(result_files)}"
    )

    errors = []

    if program_count == 0:

        errors.append(
            "NO USABLE PROGRAM RECORDS FOUND"
        )

    if result_count == 0:

        errors.append(
            "NO USABLE RESULT RECORDS FOUND"
        )

    if errors:

        print("\nPIPELINE VALIDATION FAILED")

        for error in errors:

            print(
                f" - {error}"
            )

        raise RuntimeError(
            "Pipeline stopped because required "
            "structured data is missing."
        )

    print(
        "\nPIPELINE VALIDATION PASSED"
    )

    return True
