import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize_text(value):
    """Normalize text for reliable comparisons."""

    if not value:
        return ""

    value = str(value).upper().strip()

    # Remove accents
    value = unicodedata.normalize(
        "NFD",
        value
    )

    value = "".join(
        char
        for char in value
        if unicodedata.category(char) != "Mn"
    )

    # Normalize separators
    value = value.replace("-", " ")
    value = value.replace("_", " ")

    # Remove special characters
    value = re.sub(
        r"[^A-Z0-9 ]",
        " ",
        value
    )

    # Collapse spaces
    value = re.sub(
        r"\s+",
        " ",
        value
    ).strip()

    return value


# ============================================================
# TRACK NORMALIZATION
# ============================================================

def normalize_track(track):
    """Normalize track names and common variations."""

    track = normalize_text(track)

    if not track:
        return ""

    aliases = {

        "PARIS VINCENNES NOCTURNE":
            "PARIS VINCENNES",

        "VINCENNES NOCTURNE":
            "PARIS VINCENNES",

        "VINCENNES":
            "PARIS VINCENNES",

        "PARIS LONGCHAMP":
            "PARISLONGCHAMP",

        "LONGCHAMP":
            "PARISLONGCHAMP",

        "AUTEUIL":
            "AUTEUIL",

        "CRAON":
            "CRAON",

        "LA CAPELLE":
            "LA CAPELLE",
    }

    return aliases.get(
        track,
        track
    )


# ============================================================
# DATE NORMALIZATION
# ============================================================

def normalize_date(value):
    """Normalize dates to YYYY-MM-DD."""

    if not value:
        return None

    value = str(value).strip()

    formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d.%m.%Y",
    ]

    for date_format in formats:

        try:

            return datetime.strptime(
                value,
                date_format
            ).strftime(
                "%Y-%m-%d"
            )

        except ValueError:
            pass

    return value


# ============================================================
# GET TRACK
# IMPORTANT:
# Program parser stores track inside:
#
# race["race"]["track"]
#
# Result parser may store it at:
#
# race["track"]
# ============================================================

def get_track(race):
    """Get track from top-level or nested race data."""

    # First try top-level
    track = race.get("track")

    if track:
        return track

    # Then try nested program structure
    race_info = race.get("race")

    if isinstance(
        race_info,
        dict
    ):

        return race_info.get(
            "track"
        )

    return None


# ============================================================
# GET RACE NUMBER
# ============================================================

def get_race_number(race):
    """Extract race number safely."""

    # --------------------------------------------------------
    # TRY TOP-LEVEL FIELDS
    # --------------------------------------------------------

    for key in [
        "race_number",
        "number",
    ]:

        value = race.get(key)

        if value is not None:

            match = re.search(
                r"\d+",
                str(value)
            )

            if match:

                return int(
                    match.group()
                )

    # --------------------------------------------------------
    # TRY NESTED PROGRAM STRUCTURE
    # --------------------------------------------------------

    race_info = race.get(
        "race"
    )

    if isinstance(
        race_info,
        dict
    ):

        value = race_info.get(
            "race_number"
        )

        if value is not None:

            match = re.search(
                r"\d+",
                str(value)
            )

            if match:

                return int(
                    match.group()
                )

    return None


# ============================================================
# GET HORSE NAMES
# ============================================================

def get_horse_names(race):
    """Extract normalized horse names."""

    horses = race.get(
        "horses",
        []
    )

    names = set()

    for horse in horses:

        if isinstance(
            horse,
            dict
        ):

            name = (
                horse.get("name")
                or horse.get("horse")
                or horse.get("horse_name")
            )

            if name:

                names.add(
                    normalize_text(name)
                )

        elif isinstance(
            horse,
            str
        ):

            names.add(
                normalize_text(horse)
            )

    return names


# ============================================================
# MATCH CALCULATION
# ============================================================

def calculate_match(
    program_race,
    result_race,
):
    """Calculate confidence score."""

    # --------------------------------------------------------
    # GET DATES
    # --------------------------------------------------------

    program_date = normalize_date(
        program_race.get("date")
    )

    result_date = normalize_date(
        result_race.get("date")
    )

    # --------------------------------------------------------
    # GET TRACKS
    # --------------------------------------------------------

    program_track = normalize_track(
        get_track(program_race)
    )

    result_track = normalize_track(
        get_track(result_race)
    )

    # --------------------------------------------------------
    # GET RACE NUMBERS
    # --------------------------------------------------------

    program_number = get_race_number(
        program_race
    )

    result_number = get_race_number(
        result_race
    )

    # --------------------------------------------------------
    # SAFETY:
    # DO NOT MATCH WITHOUT TRACK
    # --------------------------------------------------------

    if not program_track:

        return {
            "score": 0,
            "max_score": 100,
            "confidence": 0,
            "reasons": [
                "program track missing"
            ],
        }

    if not result_track:

        return {
            "score": 0,
            "max_score": 100,
            "confidence": 0,
            "reasons": [
                "result track missing"
            ],
        }

    # --------------------------------------------------------
    # START SCORE
    # --------------------------------------------------------

    score = 0

    reasons = []

    # --------------------------------------------------------
    # DATE = 40 POINTS
    # --------------------------------------------------------

    if (
        program_date
        and result_date
        and program_date == result_date
    ):

        score += 40

        reasons.append(
            "date exact"
        )

    # --------------------------------------------------------
    # TRACK = 30 POINTS
    # --------------------------------------------------------

    if program_track == result_track:

        score += 30

        reasons.append(
            "track exact"
        )

    # --------------------------------------------------------
    # RACE NUMBER = 20 POINTS
    # --------------------------------------------------------

    if (
        program_number is not None
        and result_number is not None
        and program_number == result_number
    ):

        score += 20

        reasons.append(
            "race number exact"
        )

    # --------------------------------------------------------
    # HORSE OVERLAP = 10 POINTS
    # --------------------------------------------------------

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

        overlap = (
            len(
                program_horses
                & result_horses
            )
            /
            min(
                len(program_horses),
                len(result_horses),
            )
        )

        horse_score = round(
            overlap * 10
        )

        score += horse_score

        if horse_score:

            reasons.append(
                f"horse overlap {overlap:.0%}"
            )

    # --------------------------------------------------------
    # CONFIDENCE
    # Score is already out of 100
    # --------------------------------------------------------

    confidence = score

    return {
        "score": score,
        "max_score": 100,
        "confidence": confidence,
        "reasons": reasons,
    }


# ============================================================
# LOAD JSON FILES
# ============================================================

def load_json_files(folder):
    """Load all JSON files from folder."""

    folder = Path(folder)

    records = []

    for path in folder.glob(
        "*.json"
    ):

        try:

            with open(
                path,
                "r",
                encoding="utf-8"
            ) as file:

                data = json.load(
                    file
                )

            if isinstance(
                data,
                list
            ):

                records.extend(
                    data
                )

            elif isinstance(
                data,
                dict
            ):

                records.append(
                    data
                )

        except Exception as error:

            print(
                f"Failed loading "
                f"{path.name}: "
                f"{error}"
            )

    return records


# ============================================================
# DEDUPLICATE RACES
# ============================================================

def deduplicate_races(races):
    """Remove duplicate races."""

    unique = {}

    result = []

    for race in races:

        key = (

            normalize_date(
                race.get("date")
            ),

            normalize_track(
                get_track(race)
            ),

            get_race_number(
                race
            ),
        )

        # Keep incomplete records
        if not all(key):

            result.append(
                race
            )

            continue

        if key not in unique:

            unique[key] = race

            result.append(
                race
            )

    return result


# ============================================================
# CLASSIFY UNMATCHED RACES
# ============================================================

def classify_unmatched(
    program_race
):

    race_date = normalize_date(
        program_race.get("date")
    )

    if race_date:

        try:

            race_datetime = (
                datetime.strptime(
                    race_date,
                    "%Y-%m-%d"
                )
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

    # IMPORTANT:
    # Use get_track instead of
    # program_race.get("track")
    if not get_track(
        program_race
    ):

        return (
            "PARSER_DATA_MISSING"
        )

    return (
        "RESULT_NOT_FOUND"
    )


# ============================================================
# MATCH RACES
# ============================================================

def match_races(
    programs,
    results,
    threshold=75,
):

    matched = []

    unmatched = []

    for program in programs:

        best_match = None

        best_result = None

        for result in results:

            match_info = (
                calculate_match(
                    program,
                    result,
                )
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

                best_match = (
                    match_info
                )

                best_result = (
                    result
                )

        # ----------------------------------------------------
        # ACCEPT MATCH
        # ----------------------------------------------------

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

            print(

                f"MATCHED "
                f"{normalize_date(program.get('date'))} | "
                f"{get_track(program)} | "
                f"Race {get_race_number(program)} | "
                f"{best_match['confidence']}%"
            )

        # ----------------------------------------------------
        # UNMATCHED
        # ----------------------------------------------------

        else:

            status = (
                classify_unmatched(
                    program
                )
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

            confidence = (

                best_match[
                    "confidence"
                ]

                if best_match

                else 0
            )

            print(

                f"UNMATCHED "
                f"[{status}] "
                f"{normalize_date(program.get('date'))} | "
                f"{get_track(program)} | "
                f"Race {get_race_number(program)} | "
                f"Best confidence: "
                f"{confidence}%"
            )

    return (
        matched,
        unmatched,
    )


# ============================================================
# RUN MATCHING ENGINE
# ============================================================

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

    print(
        "\n" + "=" * 60
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

    programs = load_json_files(
        programs_path
    )

    results = load_json_files(
        results_path
    )

    print(
        f"\nPrograms loaded: "
        f"{len(programs)}"
    )

    print(
        f"Results loaded: "
        f"{len(results)}"
    )

    programs = (
        deduplicate_races(
            programs
        )
    )

    results = (
        deduplicate_races(
            results
        )
    )

    print(
        f"Unique programs: "
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

    matched, unmatched = (
        match_races(

            programs,

            results,

            threshold=75,
        )
    )

    Path(
        output_path
    ).parent.mkdir(

        parents=True,

        exist_ok=True,
    )

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

    print(
        "\n" + "=" * 60
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


# ============================================================
# DIRECT EXECUTION
# ============================================================

if __name__ == "__main__":

    run_matching()
