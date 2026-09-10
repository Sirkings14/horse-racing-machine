import json

from pathlib import Path


# ============================================================
# IMPORT RACE HELPERS
# ============================================================

from src.matching.race_matcher import (

    get_race_date,

    get_race_number,

    get_race_track,

    get_horse_names,

    is_valid_race_record,

    extract_race_records,

)


# ============================================================
# LOAD JSON FILES
# ============================================================


def load_records(folder):
    """
    Load race records from all JSON files
    inside a folder.
    """

    folder = Path(
        folder
    )

    records = []

    diagnostics = {

        "files_found": 0,

        "files_loaded": 0,

        "files_failed": 0,

        "files_without_records": 0,

        "invalid_records": 0,

    }

    # --------------------------------------------------------
    # FOLDER CHECK
    # --------------------------------------------------------

    if not folder.exists():

        diagnostics[
            "folder_missing"
        ] = True

        return (

            records,

            diagnostics,

        )

    diagnostics[
        "folder_missing"
    ] = False

    json_files = list(

        folder.glob(
            "*.json"
        )

    )

    diagnostics[
        "files_found"
    ] = len(
        json_files
    )

    # --------------------------------------------------------
    # LOAD FILES
    # --------------------------------------------------------

    for path in json_files:

        try:

            with open(

                path,

                "r",

                encoding="utf-8",

            ) as file:

                data = json.load(
                    file
                )

            extracted = extract_race_records(
                data
            )

            if not extracted:

                diagnostics[
                    "files_without_records"
                ] += 1

                print(

                    f"WARNING: No race records "
                    f"found in {path.name}"

                )

                continue

            valid_records = []

            for record in extracted:

                if is_valid_race_record(
                    record
                ):

                    valid_records.append(
                        record
                    )

                else:

                    diagnostics[
                        "invalid_records"
                    ] += 1

            if valid_records:

                records.extend(
                    valid_records
                )

                diagnostics[
                    "files_loaded"
                ] += 1

            else:

                diagnostics[
                    "files_without_records"
                ] += 1

                print(

                    f"WARNING: No valid race records "
                    f"in {path.name}"

                )

        except Exception as error:

            diagnostics[
                "files_failed"
            ] += 1

            print(

                f"ERROR loading "
                f"{path.name}: "
                f"{error}"

            )

    return (

        records,

        diagnostics,

    )


# ============================================================
# VALIDATE PROGRAM RECORDS
# ============================================================


def validate_programs(
    programs,
):
    """
    Validate program race records.
    """

    errors = []

    warnings = []

    if not programs:

        errors.append(

            "No valid program races found."

        )

        return {

            "valid": False,

            "errors": errors,

            "warnings": warnings,

            "count": 0,

        }

    missing_track = 0

    missing_horses = 0

    for race in programs:

        if not get_race_date(
            race
        ):

            errors.append(

                "Program race missing date."

            )

        if (

            get_race_number(
                race
            )
            is None

        ):

            errors.append(

                "Program race missing "
                "race number."

            )

        if not get_race_track(
            race
        ):

            missing_track += 1

        if not get_horse_names(
            race
        ):

            missing_horses += 1

    if missing_track:

        warnings.append(

            f"{missing_track} program race(s) "
            f"missing track information."

        )

    if missing_horses:

        warnings.append(

            f"{missing_horses} program race(s) "
            f"missing horse information."

        )

    return {

        "valid":
            len(errors) == 0,

        "errors":
            errors,

        "warnings":
            warnings,

        "count":
            len(programs),

    }


# ============================================================
# VALIDATE RESULT RECORDS
# ============================================================


def validate_results(
    results,
):
    """
    Validate result race records.
    """

    errors = []

    warnings = []

    # --------------------------------------------------------
    # CRITICAL CHECK
    # --------------------------------------------------------

    if not results:

        errors.append(

            "No valid result races found. "
            "Results parser output is empty "
            "or does not contain recognizable "
            "date + race number fields."

        )

        return {

            "valid": False,

            "errors": errors,

            "warnings": warnings,

            "count": 0,

        }

    missing_track = 0

    missing_horses = 0

    for race in results:

        if not get_race_date(
            race
        ):

            errors.append(

                "Result race missing date."

            )

        if (

            get_race_number(
                race
            )
            is None

        ):

            errors.append(

                "Result race missing "
                "race number."

            )

        if not get_race_track(
            race
        ):

            missing_track += 1

        if not get_horse_names(
            race
        ):

            missing_horses += 1

    if missing_track:

        warnings.append(

            f"{missing_track} result race(s) "
            f"missing track information."

        )

    if missing_horses:

        warnings.append(

            f"{missing_horses} result race(s) "
            f"missing horse information."

        )

    return {

        "valid":
            len(errors) == 0,

        "errors":
            errors,

        "warnings":
            warnings,

        "count":
            len(results),

    }


# ============================================================
# PRINT DIAGNOSTICS
# ============================================================


def print_diagnostics(
    title,
    diagnostics,
):
    """
    Print file loading diagnostics.
    """

    print(
        "\n"
        + "-" * 60
    )

    print(
        title
    )

    print(
        "-" * 60
    )

    if diagnostics.get(
        "folder_missing"
    ):

        print(
            "FOLDER DOES NOT EXIST"
        )

        return

    print(

        f"JSON files found: "

        f"{diagnostics.get('files_found', 0)}"

    )

    print(

        f"Files loaded: "

        f"{diagnostics.get('files_loaded', 0)}"

    )

    print(

        f"Files failed: "

        f"{diagnostics.get('files_failed', 0)}"

    )

    print(

        f"Files without valid races: "

        f"{diagnostics.get('files_without_records', 0)}"

    )

    print(

        f"Invalid records ignored: "

        f"{diagnostics.get('invalid_records', 0)}"

    )


# ============================================================
# MAIN PIPELINE VALIDATOR
# ============================================================


def validate_pipeline(

    programs_path=
        "data/structured/programs",

    results_path=
        "data/structured/results",

):
    """
    Validate all pipeline data before
    allowing the matching engine to run.

    Returns:

    {
        "valid": bool,
        "programs": {...},
        "results": {...},
        "errors": [...],
        "warnings": [...]
    }
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

    # --------------------------------------------------------
    # LOAD PROGRAMS
    # --------------------------------------------------------

    print(
        "\nVALIDATING PROGRAM DATA"
    )

    programs, program_diagnostics = load_records(

        programs_path

    )

    print_diagnostics(

        "PROGRAM FILE DIAGNOSTICS",

        program_diagnostics,

    )

    # --------------------------------------------------------
    # LOAD RESULTS
    # --------------------------------------------------------

    print(
        "\nVALIDATING RESULT DATA"
    )

    results, result_diagnostics = load_records(

        results_path

    )

    print_diagnostics(

        "RESULT FILE DIAGNOSTICS",

        result_diagnostics,

    )

    # --------------------------------------------------------
    # VALIDATE RECORDS
    # --------------------------------------------------------

    program_validation = validate_programs(

        programs

    )

    result_validation = validate_results(

        results

    )

    # --------------------------------------------------------
    # COMBINE ERRORS
    # --------------------------------------------------------

    errors = []

    warnings = []

    for error in program_validation[
        "errors"
    ]:

        errors.append(

            f"PROGRAM: {error}"

        )

    for error in result_validation[
        "errors"
    ]:

        errors.append(

            f"RESULT: {error}"

        )

    for warning in program_validation[
        "warnings"
    ]:

        warnings.append(

            f"PROGRAM: {warning}"

        )

    for warning in result_validation[
        "warnings"
    ]:

        warnings.append(

            f"RESULT: {warning}"

        )

    # --------------------------------------------------------
    # FINAL STATUS
    # --------------------------------------------------------

    valid = (

        program_validation[
            "valid"
        ]

        and

        result_validation[
            "valid"
        ]

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

        f"\nValid program races: "

        f"{program_validation['count']}"

    )

    print(

        f"Valid result races: "

        f"{result_validation['count']}"

    )

    # --------------------------------------------------------
    # ERRORS
    # --------------------------------------------------------

    if errors:

        print(
            "\nCRITICAL ERRORS:"
        )

        for error in errors:

            print(

                f"  - {error}"

            )

    # --------------------------------------------------------
    # WARNINGS
    # --------------------------------------------------------

    if warnings:

        print(
            "\nWARNINGS:"
        )

        for warning in warnings:

            print(

                f"  - {warning}"

            )

    # --------------------------------------------------------
    # FINAL RESULT
    # --------------------------------------------------------

    print(
        "\n"
        + "=" * 60
    )

    if valid:

        print(
            "PIPELINE VALIDATION PASSED"
        )

    else:

        print(
            "PIPELINE VALIDATION FAILED"
        )

    print(
        "=" * 60
    )

    return {

        "valid":
            valid,

        "programs":
            program_validation,

        "results":
            result_validation,

        "errors":
            errors,

        "warnings":
            warnings,

        "program_diagnostics":
            program_diagnostics,

        "result_diagnostics":
            result_diagnostics,

    }


# ============================================================
# DIRECT EXECUTION
# ============================================================


if __name__ == "__main__":

    validation = validate_pipeline()

    if validation[
        "valid"
    ]:

        print(

            "\nValidation successful."

        )

    else:

        print(

            "\nValidation failed."

        )
