import json
import re
import unicodedata

from datetime import datetime
from pathlib import Path


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize_text(value):

    if not value:
        return ""

    value = str(value).upper().strip()

    value = unicodedata.normalize(
        "NFD",
        value,
    )

    value = "".join(
        char
        for char in value
        if unicodedata.category(char) != "Mn"
    )

    value = value.replace(
        "-",
        " ",
    )

    value = value.replace(
        "_",
        " ",
    )

    value = re.sub(
        r"[^A-Z0-9 ]",
        " ",
        value,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    ).strip()

    return value


# ============================================================
# TRACK NORMALIZATION
# ============================================================

def normalize_track(track):

    track = normalize_text(
        track
    )

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

        "PARIS LONGCHAMP NOCTURNE":
            "PARISLONGCHAMP",

    }

    return aliases.get(
        track,
        track,
    )


# ============================================================
# DATE NORMALIZATION
# ============================================================

def normalize_date(value):

    if not value:
        return None

    value = str(
        value
    ).strip()

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
                date_format,
            ).strftime(
                "%Y-%m-%d"
            )

        except ValueError:

            pass

    return None


# ============================================================
# EXTRACT RACE NUMBER
# ============================================================

def get_race_number(race):

    if not isinstance(
        race,
        dict,
    ):
        return None

    locations = [

        race,

        race.get(
            "race",
            {},
        ),

    ]

    for location in locations:

        if not isinstance(
            location,
            dict,
        ):
            continue

        for key in [

            "race_number",

            "number",

            "race",

        ]:

            value = location.get(
                key
            )

            if value is None:
                continue

            match = re.search(
                r"\d+",
                str(value),
            )

            if match:

                return int(
                    match.group()
                )

    return None


# ============================================================
# EXTRACT DATE
# ============================================================

def get_race_date(race):

    if not isinstance(
        race,
        dict,
    ):
        return None

    value = race.get(
        "date"
    )

    if value:

        return normalize_date(
            value
        )

    nested = race.get(
        "race",
        {}
    )

    if isinstance(
        nested,
        dict,
    ):

        return normalize_date(
            nested.get(
                "date"
            )
        )

    return None


# ============================================================
# EXTRACT TRACK
# ============================================================

def get_race_track(race):

    if not isinstance(
        race,
        dict,
    ):
        return ""

    value = race.get(
        "track"
    )

    if value:

        return normalize_track(
            value
        )

    nested = race.get(
        "race",
        {}
    )

    if isinstance(
        nested,
        dict,
    ):

        return normalize_track(
            nested.get(
                "track"
            )
        )

    return ""


# ============================================================
# EXTRACT HORSES
# ============================================================

def get_horse_names(race):

    horses = race.get(
        "horses",
        [],
    )

    if not horses:

        nested = race.get(
            "race",
            {},
        )

        if isinstance(
            nested,
            dict,
        ):

            horses = nested.get(
                "horses",
                [],
            )

    names = set()

    for horse in horses:

        if isinstance(
            horse,
            dict,
        ):

            name = (

                horse.get(
                    "name"
                )

                or horse.get(
                    "horse"
                )

                or horse.get(
                    "horse_name"
                )

            )

            if name:

                names.add(
                    normalize_text(
                        name
                    )
                )

        elif isinstance(
            horse,
            str,
        ):

            names.add(
                normalize_text(
                    horse
                )
            )

    return names


# ============================================================
# LOAD JSON FILES
# ============================================================

def load_json_files(folder):

    folder = Path(
        folder
    )

    records = []

    for path in folder.glob(
        "*.json"
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

        except Exception as error:

            print(
                f"Failed loading "
                f"{path.name}: "
                f"{error}"
            )

    return records


# ============================================================
# CREATE RACE IDENTITY KEY
# ============================================================

def create_race_key(race):

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


# ============================================================
# DEDUPLICATE RACES
# ============================================================

def deduplicate_races(races):

    unique = {}

    for race in races:

        date = get_race_date(
            race
        )

        track = get_race_track(
            race
        )

        number = get_race_number(
            race
        )

        # Do not trust incomplete races
        # as unique identities.

        if not date:

            continue

        if number is None:

            continue

        key = (

            date,

            track,

            number,

        )

        # Prefer the record with more horses.

        if key not in unique:

            unique[key] = race

        else:

            existing_horses = len(
                get_horse_names(
                    unique[key]
                )
            )

            new_horses = len(
                get_horse_names(
                    race
                )
            )

            if new_horses > existing_horses:

                unique[key] = race

    return list(
        unique.values()
    )


# ============================================================
# CHECK EXACT CORE IDENTITY
# ============================================================

def core_identity_matches(
    program,
    result,
):

    program_date = get_race_date(
        program
    )

    result_date = get_race_date(
        result
    )

    program_track = get_race_track(
        program
    )

    result_track = get_race_track(
        result
    )

    program_number = get_race_number(
        program
    )

    result_number = get_race_number(
        result
    )

    if not program_date:
        return False

    if not result_date:
        return False

    if program_date != result_date:
        return False

    if (
        program_number is not None
        and result_number is not None
        and program_number != result_number
    ):
        return False

    # If both tracks exist,
    # they MUST match.

    if (
        program_track
        and result_track
        and program_track != result_track
    ):
        return False

    return True


# ============================================================
# CALCULATE HORSE OVERLAP
# ============================================================

def calculate_horse_overlap(
    program,
    result,
):

    program_horses = get_horse_names(
        program
    )

    result_horses = get_horse_names(
        result
    )

    if not program_horses:

        return 0

    if not result_horses:

        return 0

    common = (

        program_horses
        & result_horses

    )

    overlap = (

        len(common)
        / min(
            len(program_horses),
            len(result_horses),
        )

    )

    return round(
        overlap * 100,
        2,
    )


# ============================================================
# CALCULATE MATCH
# ============================================================

def calculate_match(
    program,
    result,
):

    if not core_identity_matches(
        program,
        result,
    ):

        return {

            "confidence": 0,

            "horse_overlap": 0,

            "reasons": [

                "core identity mismatch"

            ],

        }

    program_track = get_race_track(
        program
    )

    result_track = get_race_track(
        result
    )

    program_number = get_race_number(
        program
    )

    result_number = get_race_number(
        result
    )

    score = 60

    reasons = [

        "date exact"

    ]

    # Track

    if program_track and result_track:

        score += 20

        reasons.append(
            "track exact"
        )

    # Race number

    if (

        program_number is not None

        and result_number is not None

        and program_number == result_number

    ):

        score += 10

        reasons.append(
            "race number exact"
        )

    # Horses

    horse_overlap = calculate_horse_overlap(

        program,

        result,

    )

    if horse_overlap > 0:

        horse_points = round(

            horse_overlap
            * 0.1

        )

        score += horse_points

        reasons.append(

            f"horse overlap "
            f"{horse_overlap}%"

        )

    confidence = min(
        score,
        100,
    )

    return {

        "confidence":
            confidence,

        "horse_overlap":
            horse_overlap,

        "reasons":
            reasons,

    }


# ============================================================
# CLASSIFY UNMATCHED
# ============================================================

def classify_unmatched(
    program,
):

    race_date = get_race_date(
        program
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

                return "FUTURE_RACE"

        except ValueError:

            pass

    if not get_race_track(
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
    threshold=75,
):

    matched = []

    unmatched = []

    used_results = set()

    for program in programs:

        best_match = None

        best_result = None

        best_index = None

        for index, result in enumerate(
            results
        ):

            if index in used_results:

                continue

            match_info = calculate_match(

                program,

                result,

            )

            if not best_match:

                best_match = match_info

                best_result = result

                best_index = index

                continue

            if (

                match_info[
                    "confidence"
                ]

                > best_match[
                    "confidence"
                ]

            ):

                best_match = match_info

                best_result = result

                best_index = index

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

            used_results.add(
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

                confidence = best_match.get(

                    "confidence",

                    0,

                )

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


# ============================================================
# RUN MATCHING ENGINE
# ============================================================

def run_matching(

    programs_path=
        "data/structured/programs",

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

    programs = deduplicate_races(
        programs
    )

    results = deduplicate_races(
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

    print(
        "\nMATCHING RACES"
    )

    print(
        "=" * 60
    )

    matched, unmatched = match_races(

        programs,

        results,

        threshold=75,

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


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    run_matching()
