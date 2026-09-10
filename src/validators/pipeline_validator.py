import json
from pathlib import Path

from src.utils.race_utils import (
    expand_records,
    get_race_date,
    get_race_number,
    get_race_track,
)


def load_json_files(folder):
    """
    Load JSON files and keep diagnostics.
    """

    folder = Path(
        folder
    )

    records = []

    diagnostics = {

        "files_found": 0,

        "files_loaded": 0,

        "files_failed": 0,

        "files_without_valid_races": 0,

        "invalid_records": 0,

    }

    for path in folder.glob(
        "*.json"
    ):

        diagnostics[
            "files_found"
        ] += 1

        try:

            with open(
                path,
                "r",
                encoding="utf-8",
            ) as file:

                data = json.load(
                    file
                )

            diagnostics[
                "files_loaded"
            ] += 1

            if isinstance(
                data,
                list,
            ):

                records.extend(
                    data
                )

            elif isinstance(
                data,
                dict,
            ):

                records.append(
                    data
                )

        except Exception as error:

            diagnostics[
                "files_failed"
            ] += 1

            print(

                f"WARNING: Failed loading "
                f"{path.name}: {error}"

            )

    return records, diagnostics


def is_valid_race(record):
    """
    A valid race requires:

    - date
    - race number

    Track is allowed to be missing,
    but will generate a warning.
    """

    date = get_race_date(
        record
    )

    race_number = get_race_number(
        record
    )

    return (

        date is not None

        and race_number is not None

    )


def validate_records(
    records,
    diagnostics,
    record_type,
):
    """
    Expand and validate race records.
    """

    expanded_records = expand_records(
        records
    )

    valid_records = []

    missing_track = 0

    for record in expanded_records:

        if not isinstance(
            record,
            dict,
        ):

            diagnostics[
                "invalid_records"
            ] += 1

            continue

        if not is_valid_race(
            record
        ):

            diagnostics[
                "invalid_records"
            ] += 1

            continue

        track = get_race_track(
            record
        )

        if not track:

            missing_track += 1

        valid_records.append(
            record
        )

    return (

        valid_records,

        missing_track,

    )


def print_diagnostics(
    title,
    diagnostics,
):
    """
    Print validation diagnostics.
    """

    print(
        "\n"
        + "-" * 60
    )

    print(
        f"{title} FILE DIAGNOSTICS"
    )

    print(
        "-" * 60
    )

    print(

        f"JSON files found: "
        f"{diagnostics['files_found']}"

    )

    print(

        f"Files loaded: "
        f"{diagnostics['files_loaded']}"

    )

    print(

        f"Files failed: "
        f"{diagnostics['files_failed']}"

    )

    print(

        f"Invalid records ignored: "
        f"{diagnostics['invalid_records']}"

    )


def validate_pipeline(
    programs_path=
        "data/structured/programs",

    results_path=
        "data/structured/results",

):
    """
    Validate the entire pipeline before
    the race matching engine runs.
    """

    print(
        "\n"
        + "=" * 60
    )

    print(
        "HORSE RACING MACHINE"
    )

    print(
        "PIPELINE VALIDATION ENGINE"
    )

    print(
        "=" * 60
    )

    print(
        "\nVALIDATING PROGRAM DATA"
    )

    program_records, program_diagnostics = (
        load_json_files(
            programs_path
        )
    )

    valid_programs, programs_missing_track = (
        validate_records(

            program_records,

            program_diagnostics,

            "PROGRAM",

        )
    )

    print_diagnostics(

        "PROGRAM",

        program_diagnostics,

    )

    print(
        "\nVALIDATING RESULT DATA"
    )

    result_records, result_diagnostics = (
        load_json_files(
            results_path
        )
    )

    valid_results, results_missing_track = (
        validate_records(

            result_records,

            result_diagnostics,

            "RESULT",

        )
    )

    print_diagnostics(

        "RESULT",

        result_diagnostics,

    )

    errors = []

    warnings = []

    if not valid_programs:

        errors.append(

            "PROGRAM: No valid program "
            "races found."

        )

    if not valid_results:

        errors.append(

            "RESULT: No valid result "
            "races found."

        )

    if programs_missing_track:

        warnings.append(

            f"PROGRAM: "
            f"{programs_missing_track} "
            f"program race(s) missing "
            f"track information."

        )

    if results_missing_track:

        warnings.append(

            f"RESULT: "
            f"{results_missing_track} "
            f"result race(s) missing "
            f"track information."

        )

    print(
        "\n"
        + "=" * 60
    )

    print(
        "VALIDATION SUMMARY"
    )

    print(
        "=" * 60
    )

    print(

        f"Valid program races: "
        f"{len(valid_programs)}"

    )

    print(

        f"Valid result races: "
        f"{len(valid_results)}"

    )

    if errors:

        print(
            "\nCRITICAL ERRORS:"
        )

        for error in errors:

            print(
                f"  - {error}"
            )

    if warnings:

        print(
            "\nWARNINGS:"
        )

        for warning in warnings:

            print(
                f"  - {warning}"
            )

    if errors:

        print(
            "\n"
            + "=" * 60
        )

        print(
            "PIPELINE VALIDATION FAILED"
        )

        print(
            "=" * 60
        )

        return {

            "valid":
                False,

            "programs":
                valid_programs,

            "results":
                valid_results,

            "errors":
                errors,

            "warnings":
                warnings,

        }

    print(
        "\n"
        + "=" * 60
    )

    print(
        "PIPELINE VALIDATION PASSED"
    )

    print(
        "=" * 60
    )

    return {

        "valid":
            True,

        "programs":
            valid_programs,

        "results":
            valid_results,

        "errors":
            errors,

        "warnings":
            warnings,

    }
