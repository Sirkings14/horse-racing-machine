import json
import re
from datetime import datetime, date
from pathlib import Path


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parents[2]

PROGRAM_DIR = BASE_DIR / "data" / "parsed" / "programs"
RESULT_DIR = BASE_DIR / "data" / "parsed" / "results"

MATCHED_DIR = BASE_DIR / "data" / "matched"

MATCHED_FILE = MATCHED_DIR / "matched_races.json"
REVIEW_FILE = MATCHED_DIR / "match_review.json"


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_text(value):
    """
    Normalize text so small formatting differences do not
    prevent legitimate matches.

    Examples:

    PARIS-VINCENNES
    PARIS VINCENNES
    PARIS-VINCENNES NOCTURNE

    all become comparable.
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

    # ISO date or ISO datetime
    try:
        return datetime.fromisoformat(value).date().isoformat()
    except ValueError:
        pass

    # Common date formats
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

    records = []

    if not folder.exists():

        print(
            f"Folder not found: {folder}"
        )

        return records

    for path in sorted(
        folder.glob("*.json")
    ):

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
                f"Failed to load: "
                f"{path.name}"
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

    Keep only valid program records.
    """

    expanded = []

    for record in records:

        if not isinstance(
            record,
            dict,
        ):
            continue

        if (
            record.get("document_type")
            != "program"
        ):
            continue

        expanded.append(
            record
        )

    return expanded


def expand_result_records(records):
    """
    Result documents may contain multiple races.

    Convert:

    {
        "date": ...,
        "track": ...,
        "meeting": ...,
        "races": [...]
    }

    into one result record per race.
    """

    expanded = []

    for record in records:

        if not isinstance(
            record,
            dict,
        ):
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

        meeting = record.get(
            "meeting"
        )

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

        key = program_key(
            program
        )

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

        key = result_key(
            result
        )

        if key not in unique:

            unique[key] = result

    return list(
        unique.values()
    )


# ============================================================
# MATCHING IDENTITIES
# ============================================================

def get_program_identity(program):
    """
    Extract the identity used to match
    a program race.
    """

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
            race.get("race_number")
        ),
    }


def get_result_identity(result):
    """
    Extract the identity used to match
    a result race.
    """

    return {
        "date": normalize_date(
            result.get("date")
        ),

        "track": normalize_track(
            result.get("track")
        ),

        "race_number": safe_int(
            result.get("race_number")
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

    IMPORTANT:
    This score NEVER creates a match.

    It is used only to show the closest
    candidate inside match_review.json.

    Strict matching is handled separately.
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

    # --------------------------------------------------------
    # DATE
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # TRACK
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # RACE NUMBER
    # --------------------------------------------------------

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
        (score / max_score) * 100,
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
    Find the closest result for diagnostics.

    IMPORTANT:
    The returned candidate is NOT a match.
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

    A program race can ONLY match a result
    when ALL THREE conditions are exact:

    1. Date matches
    2. Track matches
    3. Race number matches

    Wrong dates are NEVER allowed.

    Diagnostic scores NEVER create matches.
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

    # --------------------------------------------------------
    # REQUIRE COMPLETE PROGRAM IDENTITY
    # --------------------------------------------------------

    if not program_date:

        return None

    if not program_track:

        return None

    if (
        program_race_number
        is None
    ):

        return None

    # --------------------------------------------------------
    # SEARCH RESULTS
    # --------------------------------------------------------

    for result in results:

        result_id = get_result_identity(
            result
        )

        # DATE IS REQUIRED
        if (
            result_id["date"]
            != program_date
        ):

            continue

        # TRACK IS REQUIRED
        if (
            result_id["track"]
            != program_track
        ):

            continue

        # RACE NUMBER IS REQUIRED
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

    If the race date has already passed and
    there is no exact result match, return:

    RESULT_NOT_FOUND
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
    """
    Build a verified matched race record.
    """

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
                "date":
                    program_id["date"],

                "track":
                    program_id["track"],

                "race_number":
                    program_id[
                        "race_number"
                    ],
            },

            "verification": {
                "date_match":
                    program_id["date"]
                    == result_id["date"],

                "track_match":
                    program_id["track"]
                    == result_id["track"],

                "race_number_match":
                    program_id[
                        "race_number"
                    ]
                    == result_id[
                        "race_number"
                    ],
            },
        },
    }


def build_unmatched_record(
    program,
    results,
):
    """
    Build a review record for a program
    that does not have an exact result.
    """

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

        "best_candidate":
            best_candidate,
    }


# ============================================================
# MAIN MATCHING ENGINE
# ============================================================

def run_race_matching():
    """
    Run the complete program/result
    matching engine.
    """

    print("=" * 60)

    print(
        "HORSE RACING MACHINE"
    )

    print(
        "SMART RACE MATCHING ENGINE"
    )

    print("=" * 60)

    # --------------------------------------------------------
    # CREATE OUTPUT DIRECTORY
    # --------------------------------------------------------

    MATCHED_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # LOAD DATA
    # --------------------------------------------------------

    raw_program_records = load_json_files(
        PROGRAM_DIR
    )

    raw_result_records = load_json_files(
        RESULT_DIR
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
    # EXPAND RECORDS
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

    print("=" * 60)

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

        # ----------------------------------------------------
        # EXACT MATCH FOUND
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # NO EXACT MATCH
        # ----------------------------------------------------

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

    with MATCHED_FILE.open(
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

    with REVIEW_FILE.open(
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
        f"{MATCHED_FILE}"
    )

    print(
        f"Review: "
        f"{REVIEW_FILE}"
    )

    print("=" * 60)

    return {
        "matched":
            matched_records,

        "unmatched":
            unmatched_records,
    }


# ============================================================
# PIPELINE COMPATIBILITY ENTRY POINT
# ============================================================

def run_matching():
    """
    Entry point imported and called by src.main.

    This function exists so that main.py can use:

        from src.matching.race_matcher import run_matching

    without changing the rest of the pipeline.
    """

    return run_race_matching()


# ============================================================
# DIRECT EXECUTION
# ============================================================

if __name__ == "__main__":

    run_race_matching()
