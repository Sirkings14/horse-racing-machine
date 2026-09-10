import json
from datetime import datetime
from pathlib import Path

from src.utils.race_utils import (
    expand_records,
    get_horse_names,
    get_race_date,
    get_race_number,
    get_race_track,
)


def calculate_match(
    program_race,
    result_race,
):
    """
    Calculate confidence score between
    one program race and one result race.

    Primary matching fields:

    - date
    - track
    - race number

    Horse overlap is optional because
    result files may contain only
    finishing numbers and not horse names.
    """

    program_date = get_race_date(
        program_race
    )

    result_date = get_race_date(
        result_race
    )

    program_track = get_race_track(
        program_race
    )

    result_track = get_race_track(
        result_race
    )

    program_number = get_race_number(
        program_race
    )

    result_number = get_race_number(
        result_race
    )

    score = 0
    max_score = 0

    reasons = []

    # ========================================================
    # DATE
    # ========================================================

    if program_date and result_date:

        max_score += 40

        if program_date == result_date:

            score += 40

            reasons.append(
                "date exact"
            )

    # ========================================================
    # TRACK
    # ========================================================

    if program_track and result_track:

        max_score += 30

        if program_track == result_track:

            score += 30

            reasons.append(
                "track exact"
            )

    # ========================================================
    # RACE NUMBER
    # ========================================================

    if (
        program_number is not None
        and result_number is not None
    ):

        max_score += 20

        if program_number == result_number:

            score += 20

            reasons.append(
                "race number exact"
            )

    # ========================================================
    # HORSE OVERLAP
    # ========================================================

    program_horses = get_horse_names(
        program_race
    )

    result_horses = get_horse_names(
        result_race
    )

    if (
        program_horses
        and result_horses
    ):

        max_score += 10

        overlap_count = len(
            program_horses
            & result_horses
        )

        smallest_set = min(
            len(program_horses),
            len(result_horses),
        )

        overlap = 0

        if smallest_set > 0:

            overlap = (
                overlap_count
                / smallest_set
            )

        horse_score = round(
            overlap * 10
        )

        score += horse_score

        if horse_score > 0:

            reasons.append(
                f"horse overlap {overlap:.0%}"
            )

    # ========================================================
    # CONFIDENCE
    # ========================================================

    confidence = 0

    if max_score > 0:

        confidence = round(
            (
                score
                / max_score
            )
            * 100,
            2,
        )

    return {

        "score":
            score,

        "max_score":
            max_score,

        "confidence":
            confidence,

        "reasons":
            reasons,

    }


def load_json_files(
    folder,
):
    """
    Load all JSON files from a folder.

    Each JSON file may contain:

    - one race dictionary
    - one result document containing
      multiple races
    - a list of race dictionaries
    """

    folder = Path(
        folder
    )

    records = []

    if not folder.exists():

        print(
            f"WARNING: Folder not found: "
            f"{folder}"
        )

        return records

    for path in sorted(
        folder.glob(
            "*.json"
        )
    ):

        try:

            with open(
                path,
                "r",
                encoding="utf-8",
            ) as file:

                data = json.load(
                    file
                )

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

            else:

                print(
                    f"WARNING: Unsupported JSON "
                    f"structure in {path.name}"
                )

        except Exception as error:

            print(
                f"WARNING: Failed loading "
                f"{path.name}: {error}"
            )

    return records


def create_race_key(
    race,
):
    """
    Create a stable identity key for a race.

    Preferred identity:

    date + track + race number
    """

    return (

        get_race_date(
            race
        ),

        get_race_track(
            race
        ),

        get_race_number(
            race
        ),

    )


def deduplicate_races(
    races,
):
    """
    Remove duplicate race records.

    A race must have at least:

    - date
    - race number

    Track is included whenever available.
    """

    unique = {}

    result = []

    for race in races:

        if not isinstance(
            race,
            dict,
        ):

            continue

        date = get_race_date(
            race
        )

        track = get_race_track(
            race
        )

        number = get_race_number(
            race
        )

        # Cannot safely identify the race.

        if (
            not date
            or number is None
        ):

            result.append(
                race
            )

            continue

        key = (

            date,

            track,

            number,

        )

        if key not in unique:

            unique[
                key
            ] = race

            result.append(
                race
            )

    return result


def classify_unmatched(
    program_race,
):
    """
    Determine why a program race
    could not be matched.
    """

    race_date = get_race_date(
        program_race
    )

    if race_date:

        try:

            race_datetime = datetime.strptime(

                race_date,

                "%Y-%m-%d",

            )

            if (
                race_datetime.date()
                > datetime.now().date()
            ):

                return (
                    "FUTURE_RACE"
                )

        except ValueError:

            pass

    if not get_race_track(
        program_race
    ):

        return (
            "PARSER_DATA_MISSING"
        )

    return (
        "RESULT_NOT_FOUND"
    )


def find_best_match(
    program_race,
    results,
    used_result_indexes,
):
    """
    Find the best available result
    match for one program race.
    """

    best_match = None
    best_result = None
    best_index = None

    for index, result in enumerate(
        results
    ):

        if index in used_result_indexes:

            continue

        match_info = calculate_match(

            program_race,

            result,

        )

        if (
            best_match is None
            or match_info[
                "confidence"
            ]
            >
            best_match[
                "confidence"
            ]
        ):

            best_match = match_info

            best_result = result

            best_index = index

    return (

        best_result,

        best_match,

        best_index,

    )


def match_races(
    programs,
    results,
    threshold=75,
):
    """
    Match program races against
    result races.
    """

    matched = []

    unmatched = []

    used_result_indexes = set()

    for program in programs:

        (
            best_result,

            best_match,

            best_index,

        ) = find_best_match(

            program,

            results,

            used_result_indexes,

        )

        if (
            best_match
            and best_match[
                "confidence"
            ]
            >= threshold
        ):

            matched.append({

                "program":
                    program,

                "result":
                    best_result,

                "match":
                    best_match,

            })

            if best_index is not None:

                used_result_indexes.add(
                    best_index
                )

            print(

                f"MATCHED: "

                f"{get_race_date(program)} "

                f"| "

                f"{get_race_track(program)} "

                f"| Race "

                f"{get_race_number(program)} "

                f"| "

                f"{best_match['confidence']}%"

            )

        else:

            status = classify_unmatched(
                program
            )

            unmatched.append({

                "program":
                    program,

                "status":
                    status,

                "best_candidate":

                    {

                        "result":
                            best_result,

                        "match":
                            best_match,

                    }

                    if best_result
                    else None,

            })

            confidence = 0

            if best_match:

                confidence = best_match[
                    "confidence"
                ]

            print(

                f"UNMATCHED "

                f"[{status}] "

                f"{get_race_date(program)} "

                f"| "

                f"{get_race_track(program)} "

                f"| Race "

                f"{get_race_number(program)} "

                f"| Best confidence: "

                f"{confidence}%"

            )

    return (

        matched,

        unmatched,

    )


def run_matching(

    programs_path=
        "data/structured/programs",

    results_path=
        "data/structured/results",

    output_path=
        "data/matched/matched_races.json",

    review_path=
        "data/matched/match_review.json",

):
    """
    Run the complete race matching engine.

    IMPORTANT:

    Result JSON files may contain
    multiple races under:

        {
            "date": "...",
            "track": "...",
            "races": [...]
        }

    Therefore records are expanded
    into individual races BEFORE
    deduplication and matching.
    """

    print(
        "\n"
        + "=" * 60
    )

    print(
        "HORSE RACING MACHINE"
    )

    print(
        "SMART RACE MATCHING ENGINE"
    )

    print(
        "=" * 60
    )

    # ========================================================
    # LOAD PROGRAMS
    # ========================================================

    raw_programs = load_json_files(
        programs_path
    )

    # ========================================================
    # LOAD RESULTS
    # ========================================================

    raw_results = load_json_files(
        results_path
    )

    print(

        f"\nRaw program records loaded: "
        f"{len(raw_programs)}"

    )

    print(

        f"Raw result records loaded: "
        f"{len(raw_results)}"

    )

    # ========================================================
    # EXPAND DOCUMENTS INTO INDIVIDUAL RACES
    # ========================================================

    programs = expand_records(
        raw_programs
    )

    results = expand_records(
        raw_results
    )

    print(

        f"\nExpanded program races: "
        f"{len(programs)}"

    )

    print(

        f"Expanded result races: "
        f"{len(results)}"

    )

    # ========================================================
    # DEDUPLICATE
    # ========================================================

    programs = deduplicate_races(
        programs
    )

    results = deduplicate_races(
        results
    )

    print(

        f"\nUnique programs: "
        f"{len(programs)}"

    )

    print(

        f"Unique results: "
        f"{len(results)}"

    )

    print(
        "\nMATCHING RACES"
    )

    print(
        "=" * 60
    )

    # ========================================================
    # MATCH
    # ========================================================

    matched, unmatched = match_races(

        programs,

        results,

        threshold=75,

    )

    # ========================================================
    # CREATE OUTPUT FOLDERS
    # ========================================================

    Path(
        output_path
    ).parent.mkdir(

        parents=True,

        exist_ok=True,

    )

    Path(
        review_path
    ).parent.mkdir(

        parents=True,

        exist_ok=True,

    )

    # ========================================================
    # SAVE MATCHED RACES
    # ========================================================

    with open(

        output_path,

        "w",

        encoding="utf-8",

    ) as file:

        json.dump(

            matched,

            file,

            ensure_ascii=False,

            indent=2,

        )

    # ========================================================
    # SAVE UNMATCHED RACES
    # ========================================================

    with open(

        review_path,

        "w",

        encoding="utf-8",

    ) as file:

        json.dump(

            unmatched,

            file,

            ensure_ascii=False,

            indent=2,

        )

    # ========================================================
    # SUMMARY
    # ========================================================

    print(
        "\n"
        + "=" * 60
    )

    print(
        "RACE MATCHING COMPLETE"
    )

    print(
        "=" * 60
    )

    print(

        f"Matched races: "
        f"{len(matched)}"

    )

    print(

        f"Unmatched programs: "
        f"{len(unmatched)}"

    )

    print(

        f"Saved: "
        f"{output_path}"

    )

    print(

        f"Review: "
        f"{review_path}"

    )

    return (

        matched,

        unmatched,

    )


if __name__ == "__main__":

    run_matching()
