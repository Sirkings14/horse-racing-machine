import json
import re
from datetime import datetime, date
from pathlib import Path


# ============================================================
# DEFAULT PROJECT PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parents[2]

DEFAULT_PROGRAM_DIR = BASE_DIR / "data" / "parsed" / "programs"
DEFAULT_RESULT_DIR = BASE_DIR / "data" / "parsed" / "results"

DEFAULT_MATCHED_DIR = BASE_DIR / "data" / "matched"

DEFAULT_MATCHED_FILE = (
    DEFAULT_MATCHED_DIR / "matched_races.json"
)

DEFAULT_REVIEW_FILE = (
    DEFAULT_MATCHED_DIR / "match_review.json"
)


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_text(value):
    """
    Normalize text so small formatting differences do not
    prevent legitimate matches.
    """

    if value is None:
        return ""

    value = str(value).upper().strip()

    value = value.replace("-", " ")
    value = value.replace("_", " ")

    value = re.sub(r"\s+", " ", value)

    return value.strip()


def normalize_track(track):
    """
    Normalize known track naming variations.
    """

    track = normalize_text(track)

    if not track:
        return ""

    aliases = {
        "PARIS VINCENNES NOCTURNE": "PARIS VINCENNES",
        "VINCENNES NOCTURNE": "PARIS VINCENNES",
        "PARIS VINCENNES": "PARIS VINCENNES",

        "PARISLONGCHAMP": "PARISLONGCHAMP",
        "PARIS LONGCHAMP": "PARISLONGCHAMP",

        "LA CAPELLE": "LA CAPELLE",
        "AUTEUIL": "AUTEUIL",
        "CRAON": "CRAON",
        "VIRE": "VIRE",
    }

    return aliases.get(track, track)


def normalize_date(value):
    """
    Return a clean YYYY-MM-DD string.
    """

    if value is None:
        return None

    if isinstance(value, datetime):
        return value.date().isoformat()

    if isinstance(value, date):
        return value.isoformat()

    value = str(value).strip()

    if not value:
        return None

    try:
        return datetime.fromisoformat(value).date().isoformat()
    except ValueError:
        pass

    formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(
                value,
                fmt,
            ).date().isoformat()

        except ValueError:
            continue

    return value


def safe_int(value):
    """
    Convert values to integers safely.
    """

    try:
        return int(value)

    except (TypeError, ValueError):
        return None


# ============================================================
# FILE LOADING
# ============================================================

def load_json_files(folder):
    """
    Load all JSON files from a folder.
    """

    folder = Path(folder)

    records = []

    if not folder.exists():

        print(f"Folder not found: {folder}")

        return records

    for path in sorted(folder.glob("*.json")):

        try:

            with path.open(
                "r",
                encoding="utf-8",
            ) as file:

                data = json.load(file)

            if isinstance(data, list):

                records.extend(data)

            elif isinstance(data, dict):

                records.append(data)

        except Exception as error:

            print(
                f"Failed to load: {path.name}"
            )

            print(
                f"Reason: {error}"
            )

    return records


# ============================================================
# RECORD EXPANSION
# ============================================================

def expand_program_records(records):
    """
    Program files normally represent one race.
    """

    expanded = []

    for record in records:

        if not isinstance(record, dict):
            continue

        if (
            record.get("document_type")
            != "program"
        ):
            continue

        expanded.append(record)

    return expanded


def expand_result_records(records):
    """
    Result documents may contain multiple races.

    Convert each result document into one record per race.
    """

    expanded = []

    for record in records:

        if not isinstance(record, dict):
            continue

        if (
            record.get("document_type")
            != "result"
        ):
            continue

        document_date = normalize_date(
            record.get("date")
        )

        document_track = normalize_track(
            record.get("track")
        )

        meeting = record.get("meeting")

        races = record.get(
            "races",
            [],
        )

        if not isinstance(
            races,
            list,
        ):
            continue

        for race in races:

            if not isinstance(
                race,
                dict,
            ):
                continue

            expanded.append(
                {
                    "date": document_date,

                    "track": document_track,

                    "meeting": meeting,

                    "race_number": safe_int(
                        race.get(
                            "race_number"
                        )
                    ),

                    "arrival": race.get(
                        "arrival",
                        [],
                    ),

                    "winner": race.get(
                        "winner"
                    ),

                    "second": race.get(
                        "second"
                    ),

                    "third": race.get(
                        "third"
                    ),
                }
            )

    return expanded


# ============================================================
# UNIQUE RECORDS
# ============================================================

def program_key(program):
    """
    Unique identity for a program race.
    """

    race = program.get(
        "race",
        {},
    )

    return (
        normalize_date(
            program.get("date")
        ),

        normalize_track(
            race.get("track")
        ),

        safe_int(
            race.get("race_number")
        ),
    )


def result_key(result):
    """
    Unique identity for a result race.
    """

    return (
        normalize_date(
            result.get("date")
        ),

        normalize_track(
            result.get("track")
        ),

        safe_int(
            result.get("race_number")
        ),
    )


def deduplicate_programs(programs):
    """
    Remove duplicate program races.
    """

    unique = {}

    for program in programs:

        key = program_key(program)

        if key not in unique:

            unique[key] = program

    return list(
        unique.values()
    )


def deduplicate_results(results):
    """
    Remove duplicate result races.
    """

    unique = {}

    for result in results:

        key = result_key(result)

        if key not in unique:

            unique[key] = result

    return list(
        unique.values()
    )


# ============================================================
# MATCH IDENTITIES
# ============================================================

def get_program_identity(program):

    race = program.get(
        "race",
        {},
    )

    return {
        "date": normalize_date(
            program.get("date")
        ),

        "track": normalize_track(
            race.get("track")
        ),

        "race_number": safe_int(
            race.get(
                "race_number"
            )
        ),
    }


def get_result_identity(result):

    return {
        "date": normalize_date(
            result.get("date")
        ),

        "track": normalize_track(
            result.get("track")
        ),

        "race_number": safe_int(
            result.get(
                "race_number"
            )
        ),
    }


# ============================================================
# DIAGNOSTIC SCORING
# ============================================================

def calculate_diagnostic_score(
    program,
    result,
):
    """
    Diagnostic scoring only.

    This score NEVER creates a match.

    It is only used to show the closest
    candidate inside match_review.json.
    """

    program_id = get_program_identity(
        program
    )

    result_id = get_result_identity(
        result
    )

    score = 0

    max_score = 100

    reasons = []

    if (
        program_id["date"]
        and result_id["date"]
        and program_id["date"]
        == result_id["date"]
    ):

        score += 50

        reasons.append(
            "date exact"
        )

    if (
        program_id["track"]
        and result_id["track"]
        and program_id["track"]
        == result_id["track"]
    ):

        score += 30

        reasons.append(
            "track exact"
        )

    if (
        program_id["race_number"]
        is not None
        and result_id["race_number"]
        is not None
        and program_id["race_number"]
        == result_id["race_number"]
    ):

        score += 20

        reasons.append(
            "race number exact"
        )

    confidence = round(
        (
            score
            / max_score
        )
        * 100,
        2,
    )

    return {
        "score": score,

        "max_score": max_score,

        "confidence": confidence,

        "reasons": reasons,
    }


def find_best_candidate(
    program,
    results,
):
    """
    Find closest result for diagnostics.

    This DOES NOT mean the candidate
    is a real match.
    """

    best_result = None

    best_match = None

    for result in results:

        match = calculate_diagnostic_score(
            program,
            result,
        )

        if best_match is None:

            best_result = result

            best_match = match

            continue

        if (
            match["score"]
            > best_match["score"]
        ):

            best_result = result

            best_match = match

    if best_result is None:

        return None

    return {
        "result": best_result,

        "match": best_match,
    }


# ============================================================
# STRICT MATCHING
# ============================================================

def find_exact_match(
    program,
    results,
):
    """
    STRICT MATCHING RULE.

    A race can ONLY match if:

    1. Date matches
    2. Track matches
    3. Race number matches

    Wrong dates are NEVER allowed.
    """

    program_id = get_program_identity(
        program
    )

    program_date = program_id[
        "date"
    ]

    program_track = program_id[
        "track"
    ]

    program_race_number = program_id[
        "race_number"
    ]

    if not program_date:

        return None

    if not program_track:

        return None

    if (
        program_race_number
        is None
    ):

        return None

    for result in results:

        result_id = get_result_identity(
            result
        )

        if (
            result_id["date"]
            != program_date
        ):

            continue

        if (
            result_id["track"]
            != program_track
        ):

            continue

        if (
            result_id["race_number"]
            != program_race_number
        ):

            continue

        return result

    return None


# ============================================================
# STATUS LOGIC
# ============================================================

def determine_status(program):
    """
    Determine whether a program belongs
    to a future race.
    """

    program_date = normalize_date(
        program.get("date")
    )

    if not program_date:

        return "RESULT_NOT_FOUND"

    try:

        race_date = datetime.strptime(
            program_date,
            "%Y-%m-%d",
        ).date()

        today = date.today()

        if race_date > today:

            return "FUTURE_RACE"

    except ValueError:

        pass

    return "RESULT_NOT_FOUND"


# ============================================================
# OUTPUT BUILDING
# ============================================================

def build_matched_record(
    program,
    result,
):

    program_id = get_program_identity(
        program
    )

    result_id = get_result_identity(
        result
    )

    return {
        "program": program,

        "result": result,

        "match": {

            "status": "MATCHED",

            "confidence": 100.0,

            "identity": {

                "date": program_id[
                    "date"
                ],

                "track": program_id[
                    "track"
                ],

                "race_number": program_id[
                    "race_number"
                ],
            },

            "verification": {

                "date_match": (
                    program_id["date"]
                    == result_id["date"]
                ),

                "track_match": (
                    program_id["track"]
                    == result_id["track"]
                ),

                "race_number_match": (
                    program_id[
                        "race_number"
                    ]
                    == result_id[
                        "race_number"
                    ]
                ),
            },
        },
    }


def build_unmatched_record(
    program,
    results,
):

    status = determine_status(
        program
    )

    best_candidate = find_best_candidate(
        program,
        results,
    )

    return {
        "program": program,

        "status": status,

        "best_candidate": best_candidate,
    }


# ============================================================
# MAIN MATCHING ENGINE
# ============================================================

def run_matching(
    programs_path=None,
    results_path=None,
    output_path=None,
    review_path=None,
):
    """
    Main matching function.

    Accepts optional paths so it works both:

    1. Independently
    2. When called by src/main.py
    """

    if programs_path is None:

        programs_path = (
            DEFAULT_PROGRAM_DIR
        )

    if results_path is None:

        results_path = (
            DEFAULT_RESULT_DIR
        )

    if output_path is None:

        output_path = (
            DEFAULT_MATCHED_FILE
        )

    if review_path is None:

        review_path = (
            DEFAULT_REVIEW_FILE
        )

    programs_path = Path(
        programs_path
    )

    results_path = Path(
        results_path
    )

    output_path = Path(
        output_path
    )

    review_path = Path(
        review_path
    )

    print("=" * 60)

    print(
        "HORSE RACING MACHINE"
    )

    print(
        "SMART RACE MATCHING ENGINE"
    )

    print("=" * 60)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    review_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # LOAD DATA
    # --------------------------------------------------------

    raw_program_records = load_json_files(
        programs_path
    )

    raw_result_records = load_json_files(
        results_path
    )

    print(
        f"Raw program records loaded: "
        f"{len(raw_program_records)}"
    )

    print(
        f"Raw result records loaded: "
        f"{len(raw_result_records)}"
    )

    # --------------------------------------------------------
    # EXPAND DATA
    # --------------------------------------------------------

    programs = expand_program_records(
        raw_program_records
    )

    results = expand_result_records(
        raw_result_records
    )

    print(
        f"Expanded program races: "
        f"{len(programs)}"
    )

    print(
        f"Expanded result races: "
        f"{len(results)}"
    )

    # --------------------------------------------------------
    # REMOVE DUPLICATES
    # --------------------------------------------------------

    programs = deduplicate_programs(
        programs
    )

    results = deduplicate_results(
        results
    )

    print(
        f"Unique programs: "
        f"{len(programs)}"
    )

    print(
        f"Unique results: "
        f"{len(results)}"
    )

    # --------------------------------------------------------
    # MATCH RACES
    # --------------------------------------------------------

    print(
        "MATCHING RACES"
    )

    print(
        "=" * 60
    )

    matched_records = []

    unmatched_records = []

    for program in programs:

        identity = get_program_identity(
            program
        )

        result = find_exact_match(
            program,
            results,
        )

        if result is not None:

            matched = build_matched_record(
                program,
                result,
            )

            matched_records.append(
                matched
            )

            print(
                "MATCHED: "
                f"{identity['date']} | "
                f"{identity['track']} | "
                f"Race "
                f"{identity['race_number']} | "
                "100.0%"
            )

        else:

            unmatched = build_unmatched_record(
                program,
                results,
            )

            unmatched_records.append(
                unmatched
            )

            print(
                "UNMATCHED "
                f"[{unmatched['status']}] "
                f"{identity['date']} | "
                f"{identity['track']} | "
                f"Race "
                f"{identity['race_number']}"
            )

    # --------------------------------------------------------
    # SAVE MATCHED DATA
    # --------------------------------------------------------

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            matched_records,
            file,
            indent=2,
            ensure_ascii=False,
        )

    # --------------------------------------------------------
    # SAVE REVIEW DATA
    # --------------------------------------------------------

    with review_path.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            unmatched_records,
            file,
            indent=2,
            ensure_ascii=False,
        )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    print("=" * 60)

    print(
        "RACE MATCHING COMPLETE"
    )

    print("=" * 60)

    print(
        f"Matched races: "
        f"{len(matched_records)}"
    )

    print(
        f"Unmatched programs: "
        f"{len(unmatched_records)}"
    )

    print(
        f"Saved: "
        f"{output_path}"
    )

    print(
        f"Review: "
        f"{review_path}"
    )

    print("=" * 60)

    return {
        "matched": matched_records,

        "unmatched": unmatched_records,

        "matched_count": len(
            matched_records
        ),

        "unmatched_count": len(
            unmatched_records
        ),
    }


# ============================================================
# BACKWARD COMPATIBILITY
# ============================================================

def run_race_matching():
    """
    Backward-compatible wrapper for
    older code that calls run_race_matching().
    """

    return run_matching()


# ============================================================
# DIRECT EXECUTION
# ============================================================

if __name__ == "__main__":

    run_matching()
