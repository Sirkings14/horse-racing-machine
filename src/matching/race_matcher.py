import json
import re
import unicodedata

from datetime import datetime
from pathlib import Path


# ============================================================
# TEXT NORMALIZATION
# ============================================================


def normalize_text(value):
    """
    Normalize text for reliable comparisons.
    """

    if not value:
        return ""

    value = str(
        value
    ).upper().strip()

    value = unicodedata.normalize(
        "NFD",
        value,
    )

    value = "".join(

        char

        for char in value

        if unicodedata.category(
            char
        )
        != "Mn"

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
    """
    Normalize race track names.
    """

    track = normalize_text(
        track
    )

    if not track:
        return ""

    aliases = {

        "PARIS VINCENNES":
            "PARIS VINCENNES",

        "VINCENNES":
            "PARIS VINCENNES",

        "PARIS VINCENNES NOCTURNE":
            "PARIS VINCENNES",

        "VINCENNES NOCTURNE":
            "PARIS VINCENNES",

        "PARIS LONGCHAMP":
            "PARISLONGCHAMP",

        "LONGCHAMP":
            "PARISLONGCHAMP",

        "PARISLONGCHAMP":
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
        track,
    )


# ============================================================
# DATE NORMALIZATION
# ============================================================


def normalize_date(value):
    """
    Normalize date to YYYY-MM-DD.
    """

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

        "%Y/%m/%d",

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
# SAFE FIELD ACCESS
# ============================================================


def get_nested_race(race):
    """
    Return nested race object if present.
    """

    if not isinstance(
        race,
        dict,
    ):

        return {}

    nested = race.get(
        "race"
    )

    if isinstance(
        nested,
        dict,
    ):

        return nested

    return {}


# ============================================================
# RACE NUMBER
# ============================================================


def get_race_number(race):
    """
    Extract race number safely.
    """

    if not isinstance(
        race,
        dict,
    ):

        return None

    locations = [

        race,

        get_nested_race(
            race
        ),

    ]

    possible_keys = [

        "race_number",

        "number",

        "race",

        "course_number",

    ]

    for location in locations:

        if not isinstance(
            location,
            dict,
        ):

            continue

        for key in possible_keys:

            value = location.get(
                key
            )

            if value is None:

                continue

            match = re.search(

                r"\d+",

                str(
                    value
                ),

            )

            if match:

                return int(
                    match.group()
                )

    return None


# ============================================================
# RACE DATE
# ============================================================


def get_race_date(race):
    """
    Extract race date.
    """

    if not isinstance(
        race,
        dict,
    ):

        return None

    locations = [

        race,

        get_nested_race(
            race
        ),

    ]

    possible_keys = [

        "date",

        "race_date",

        "meeting_date",

    ]

    for location in locations:

        if not isinstance(
            location,
            dict,
        ):

            continue

        for key in possible_keys:

            value = location.get(
                key
            )

            normalized = normalize_date(
                value
            )

            if normalized:

                return normalized

    return None


# ============================================================
# RACE TRACK
# ============================================================


def get_race_track(race):
    """
    Extract race track.
    """

    if not isinstance(
        race,
        dict,
    ):

        return ""

    locations = [

        race,

        get_nested_race(
            race
        ),

    ]

    possible_keys = [

        "track",

        "hippodrome",

        "racecourse",

        "course",

    ]

    for location in locations:

        if not isinstance(
            location,
            dict,
        ):

            continue

        for key in possible_keys:

            value = location.get(
                key
            )

            if value:

                return normalize_track(
                    value
                )

    return ""


# ============================================================
# HORSE NAMES
# ============================================================


def get_horse_names(race):
    """
    Extract normalized horse names.
    """

    if not isinstance(
        race,
        dict,
    ):

        return set()

    horses = race.get(
        "horses",
        []
    )

    if not horses:

        nested = get_nested_race(
            race
        )

        horses = nested.get(
            "horses",
            []
        )

    names = set()

    if not isinstance(
        horses,
        list,
    ):

        return names

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

                normalized = normalize_text(
                    name
                )

                if normalized:

                    names.add(
                        normalized
                    )

        elif isinstance(
            horse,
            str,
        ):

            normalized = normalize_text(
                horse
            )

            if normalized:

                names.add(
                    normalized
                )

    return names


# ============================================================
# RECORD IS A REAL RACE
# ============================================================


def is_valid_race_record(race):
    """
    Determine whether a record
    actually represents a usable race.
    """

    if not isinstance(
        race,
        dict,
    ):

        return False

    date = get_race_date(
        race
    )

    number = get_race_number(
        race
    )

    track = get_race_track(
        race
    )

    # Minimum requirement:
    # date + race number

    if not date:

        return False

    if number is None:

        return False

    # Track is strongly preferred.
    # Missing track is allowed because
    # some parsers may fail to extract it.

    return True


# ============================================================
# LOAD JSON FILES
# ============================================================


def extract_race_records(data):
    """
    Extract race records from different
    possible JSON structures.
    """

    records = []

    # --------------------------------------------------------
    # CASE 1
    # FILE CONTAINS A LIST
    # --------------------------------------------------------

    if isinstance(
        data,
        list,
    ):

        for item in data:

            if isinstance(
                item,
                dict,
            ):

                # Nested races list

                if isinstance(
                    item.get(
                        "races"
                    ),
                    list,
                ):

                    records.extend(
                        item[
                            "races"
                        ]
                    )

                else:

                    records.append(
                        item
                    )

        return records

    # --------------------------------------------------------
    # CASE 2
    # FILE CONTAINS A DICTIONARY
    # --------------------------------------------------------

    if isinstance(
        data,
        dict,
    ):

        # Common structure:
        # {
        #   "races": [...]
        # }

        if isinstance(
            data.get(
                "races"
            ),
            list,
        ):

            records.extend(
                data[
                    "races"
                ]
            )

            return records

        # Otherwise dictionary itself
        # may represent one race.

        records.append(
            data
        )

    return records


def load_json_files(folder):
    """
    Load and extract races from all JSON files.
    """

    folder = Path(
        folder
    )

    records = []

    files_loaded = 0

    files_failed = 0

    files_empty = 0

    if not folder.exists():

        print(
            f"\nERROR: Folder does not exist: "
            f"{folder}"
        )

        return records

    json_files = list(

        folder.glob(
            "*.json"
        )

    )

    print(

        f"\nLoading JSON files from: "
        f"{folder}"

    )

    print(

        f"JSON files found: "
        f"{len(json_files)}"

    )

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

            valid_in_file = [

                race

                for race in extracted

                if is_valid_race_record(
                    race
                )

            ]

            if not extracted:

                files_empty += 1

                print(

                    f"WARNING: No records extracted "
                    f"from {path.name}"

                )

                continue

            if not valid_in_file:

                files_empty += 1

                print(

                    f"WARNING: No valid race records "
                    f"in {path.name}"

                )

                continue

            records.extend(
                valid_in_file
            )

            files_loaded += 1

        except Exception as error:

            files_failed += 1

            print(

                f"Failed loading "
                f"{path.name}: "
                f"{error}"

            )

    print(
        "\nJSON load summary:"
    )

    print(

        f"Files loaded: "
        f"{files_loaded}"

    )

    print(

        f"Files with no valid races: "
        f"{files_empty}"

    )

    print(

        f"Files failed: "
        f"{files_failed}"

    )

    print(

        f"Valid race records: "
        f"{len(records)}"

    )

    return records


# ============================================================
# RACE KEY
# ============================================================


def create_race_key(race):
    """
    Create stable race identity key.
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


# ============================================================
# DEDUPLICATION
# ============================================================


def deduplicate_races(races):
    """
    Remove duplicate races safely.
    """

    unique = {}

    result = []

    for race in races:

        if not is_valid_race_record(
            race
        ):

            continue

        key = create_race_key(
            race
        )

        if key not in unique:

            unique[key] = race

            result.append(
                race
            )

            continue

        # ----------------------------------------------------
        # DUPLICATE HANDLING
        #
        # Keep record with more horse information.
        # ----------------------------------------------------

        existing = unique[
            key
        ]

        existing_horses = len(

            get_horse_names(
                existing
            )

        )

        new_horses = len(

            get_horse_names(
                race
            )

        )

        if new_horses > existing_horses:

            unique[
                key
            ] = race

            index = result.index(
                existing
            )

            result[
                index
            ] = race

    return result


# ============================================================
# MATCH CALCULATION
# ============================================================


def calculate_match(
    program_race,
    result_race,
):
    """
    Calculate race match confidence.
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

    # --------------------------------------------------------
    # DATE
    # --------------------------------------------------------

    if program_date and result_date:

        max_score += 40

        if program_date == result_date:

            score += 40

            reasons.append(
                "date exact"
            )

    # --------------------------------------------------------
    # TRACK
    # --------------------------------------------------------

    if program_track and result_track:

        max_score += 30

        if program_track == result_track:

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

        overlap = (

            overlap_count

            / min(

                len(
                    program_horses
                ),

                len(
                    result_horses
                ),

            )

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


# ============================================================
# UNMATCHED CLASSIFICATION
# ============================================================


def classify_unmatched(
    program_race,
):
    """
    Classify unmatched race.
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

                return "FUTURE_RACE"

        except ValueError:

            pass

    if not get_race_track(
        program_race
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
    """
    Match program races against result races.
    """

    matched = []

    unmatched = []

    used_result_indexes = set()

    for program in programs:

        best_match = None

        best_result = None

        best_index = None

        for index, result in enumerate(
            results
        ):

            if index in used_result_indexes:

                continue

            match_info = calculate_match(

                program,

                result,

            )

            if (

                best_match is None

                or match_info[
                    "confidence"
                ]

                > best_match[
                    "confidence"
                ]

            ):

                best_match = match_info

                best_result = result

                best_index = index

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

        # ----------------------------------------------------
        # NO MATCH
        # ----------------------------------------------------

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
        "data/structured/results",

    output_path=
        "data/matched/matched_races.json",

    review_path=
        "data/matched/match_review.json",

):
    """
    Run the race matching engine.
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

    # --------------------------------------------------------
    # LOAD PROGRAMS
    # --------------------------------------------------------

    programs = load_json_files(
        programs_path
    )

    # --------------------------------------------------------
    # LOAD RESULTS
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # DEDUPLICATE
    # --------------------------------------------------------

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

    # ========================================================
    # CRITICAL SAFETY CHECKS
    # ========================================================

    if not programs:

        raise RuntimeError(

            "No valid program races were found. "
            "Matching cannot continue."

        )

    if not results:

        raise RuntimeError(

            "No valid result races were found. "
            "This usually means the results parser "
            "produced the wrong JSON structure or "
            "failed to extract date/race number."

        )

    # --------------------------------------------------------
    # MATCHING
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # CREATE OUTPUT FOLDERS
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # SAVE MATCHES
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # SAVE UNMATCHED
    # --------------------------------------------------------

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

        unmatched,

    )


# ============================================================
# DIRECT EXECUTION
# ============================================================


if __name__ == "__main__":

    run_matching()
