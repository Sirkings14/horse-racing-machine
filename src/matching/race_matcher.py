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

    value = unicodedata.normalize(
        "NFD",
        value
    )

    value = "".join(
        char
        for char in value
        if unicodedata.category(char) != "Mn"
    )

    value = value.replace("-", " ")
    value = value.replace("_", " ")

    value = re.sub(
        r"[^A-Z0-9 ]",
        " ",
        value
    )

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

        # VINCENNES
        "PARIS VINCENNES NOCTURNE":
            "PARIS VINCENNES",

        "VINCENNES NOCTURNE":
            "PARIS VINCENNES",

        "PARIS VINCENNES":
            "PARIS VINCENNES",

        "VINCENNES":
            "PARIS VINCENNES",


        # LONGCHAMP
        "PARIS LONGCHAMP":
            "PARISLONGCHAMP",

        "PARISLONGCHAMP":
            "PARISLONGCHAMP",

        "LONGCHAMP":
            "PARISLONGCHAMP",


        # OTHER TRACKS
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
# SAFE FIELD EXTRACTION
# ============================================================

def get_value(record, *keys):
    """
    Get the first available value from a dictionary.
    """

    if not isinstance(
        record,
        dict
    ):
        return None

    for key in keys:

        value = record.get(key)

        if value not in [
            None,
            "",
            [],
            {},
        ]:
            return value

    return None


# ============================================================
# GET RACE OBJECT
# ============================================================

def get_race_data(record):
    """
    Some parsers store race information inside:

        {
            "race": {
                "track": "...",
                "race_number": 1
            }
        }

    Other parsers store it directly.

    This function supports both.
    """

    if not isinstance(
        record,
        dict
    ):
        return {}

    race = record.get("race")

    if isinstance(
        race,
        dict
    ):
        return race

    return record


# ============================================================
# GET DATE
# ============================================================

def get_date(record):

    value = get_value(
        record,
        "date",
        "race_date",
        "meeting_date",
    )

    return normalize_date(
        value
    )


# ============================================================
# GET TRACK
# ============================================================

def get_track(record):
    """
    Supports both nested and flat JSON structures.
    """

    race = get_race_data(
        record
    )

    value = get_value(
        race,
        "track",
        "hippodrome",
        "racecourse",
        "course",
        "venue",
    )

    if not value:

        value = get_value(
            record,
            "track",
            "hippodrome",
            "racecourse",
            "course",
            "venue",
        )

    return normalize_track(
        value
    )


# ============================================================
# GET RACE NUMBER
# ============================================================

def get_race_number(record):

    race = get_race_data(
        record
    )

    value = get_value(
        race,
        "race_number",
        "number",
        "race",
        "course_number",
    )

    if value is None:

        value = get_value(
            record,
            "race_number",
            "number",
            "course_number",
        )

    if value is None:
        return None

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
# GET HORSES
# ============================================================

def get_horse_names(record):
    """
    Extract normalized horse names.
    """

    horses = get_value(
        record,
        "horses",
        "runners",
        "participants",
        "horses_data",
    )

    if not horses:
        return set()

    names = set()

    for horse in horses:

        if isinstance(
            horse,
            dict
        ):

            name = get_value(
                horse,
                "horse",
                "name",
                "horse_name",
                "runner",
            )

            if name:

                names.add(
                    normalize_text(
                        name
                    )
                )

        elif isinstance(
            horse,
            str
        ):

            names.add(
                normalize_text(
                    horse
                )
            )

    return names


# ============================================================
# MATCH CALCULATION
# ============================================================

def calculate_match(
    program,
    result,
):
    """
    Calculate confidence between
    one program and one result.
    """

    program_date = get_date(
        program
    )

    result_date = get_date(
        result
    )

    program_track = get_track(
        program
    )

    result_track = get_track(
        result
    )

    program_number = get_race_number(
        program
    )

    result_number = get_race_number(
        result
    )

    score = 0
    max_score = 0

    reasons = []


    # --------------------------------------------------------
    # DATE
    # --------------------------------------------------------

    if (
        program_date
        and result_date
    ):

        max_score += 40

        if (
            program_date
            == result_date
        ):

            score += 40

            reasons.append(
                "date exact"
            )


    # --------------------------------------------------------
    # TRACK
    # --------------------------------------------------------

    if (
        program_track
        and result_track
    ):

        max_score += 30

        if (
            program_track
            == result_track
        ):

            score += 30

            reasons.append(
                "track exact"
            )


    # --------------------------------------------------------
    # RACE NUMBER
    # --------------------------------------------------------

    if (
        program_number
        is not None
        and result_number
        is not None
    ):

        max_score += 20

        if (
            program_number
            == result_number
        ):

            score += 20

            reasons.append(
                "race number exact"
            )


    # --------------------------------------------------------
    # HORSE OVERLAP
    # --------------------------------------------------------

    program_horses = get_horse_names(
        program
    )

    result_horses = get_horse_names(
        result
    )

    if (
        program_horses
        and result_horses
    ):

        max_score += 10

        overlap_count = len(
            program_horses
            &
            result_horses
        )

        smallest_group = min(
            len(program_horses),
            len(result_horses)
        )

        overlap = (
            overlap_count
            /
            smallest_group
        )

        horse_score = round(
            overlap * 10
        )

        score += horse_score

        if horse_score:

            reasons.append(
                f"horse overlap "
                f"{overlap:.0%}"
            )


    # --------------------------------------------------------
    # CONFIDENCE
    # --------------------------------------------------------

    confidence = 0

    if max_score > 0:

        confidence = round(
            (
                score
                /
                max_score
            )
            * 100,
            2
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

        "program_date":
            program_date,

        "result_date":
            result_date,

        "program_track":
            program_track,

        "result_track":
            result_track,

        "program_race_number":
            program_number,

        "result_race_number":
            result_number,
    }


# ============================================================
# LOAD JSON FILES
# ============================================================

def load_json_files(folder):

    folder = Path(
        folder
    )

    records = []

    if not folder.exists():

        print(
            f"Folder not found: "
            f"{folder}"
        )

        return records


    for path in sorted(
        folder.glob("*.json")
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

def deduplicate_races(records):

    unique = {}

    for record in records:

        key = (

            get_date(
                record
            ),

            get_track(
                record
            ),

            get_race_number(
                record
            ),
        )


        # Keep records with incomplete identity
        # instead of incorrectly merging them.

        if (
            not key[0]
            or not key[1]
            or key[2] is None
        ):

            unique[
                id(record)
            ] = record

            continue


        if key not in unique:

            unique[
                key
            ] = record


    return list(
        unique.values()
    )


# ============================================================
# CLASSIFY UNMATCHED
# ============================================================

def classify_unmatched(
    program
):

    race_date = get_date(
        program
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
                >
                datetime.now().date()
            ):

                return "FUTURE_RACE"

        except ValueError:
            pass


    if not get_track(
        program
    ):

        return "PARSER_DATA_MISSING"


    return "RESULT_NOT_FOUND"


# ============================================================
# MATCH RACES
# ============================================================

def match_races(
    programs,
    results,
    threshold=70,
):

    matched = []

    unmatched = []


    for program in programs:

        best_match = None

        best_result = None


        for result in results:

            match_info = calculate_match(
                program,
                result,
            )


            if (

                best_match
                is None

                or

                match_info[
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

            and

            best_match[
                "confidence"
            ]

            >=

            threshold

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

                f"MATCHED: "

                f"{get_date(program)} | "

                f"{get_track(program)} | "

                f"Race "

                f"{get_race_number(program)} | "

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


            confidence = 0

            if best_match:

                confidence = (
                    best_match[
                        "confidence"
                    ]
                )


            print(

                f"UNMATCHED "
                f"[{status}] "

                f"{get_date(program)} | "

                f"{get_track(program)} | "

                f"Race "

                f"{get_race_number(program)} | "

                f"Best confidence: "

                f"{confidence}%"
            )


    return (
        matched,
        unmatched
    )


# ============================================================
# RUN MATCHING ENGINE
# ============================================================

def run_matching(

    programs_path=
        "data/parsed/programs",

    results_path=
        "data/parsed/results",

    output_path=
        "data/matched/matched_races.json",

    review_path=
        "data/matched/match_review.json",

):

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


    # --------------------------------------------------------
    # LOAD
    # --------------------------------------------------------

    programs = (
        load_json_files(
            programs_path
        )
    )

    results = (
        load_json_files(
            results_path
        )
    )


    print(

        f"\nPrograms loaded: "

        f"{len(programs)}"
    )

    print(

        f"Results loaded: "

        f"{len(results)}"
    )


    # --------------------------------------------------------
    # DEDUPLICATE
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # MATCH
    # --------------------------------------------------------

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

            threshold=70,
        )
    )


    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

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
        unmatched
    )


# ============================================================
# DIRECT EXECUTION
# ============================================================

if __name__ == "__main__":

    run_matching()
