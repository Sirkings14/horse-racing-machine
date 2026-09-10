import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path


# ==================================================
# PATHS
# ==================================================

BASE_DIR = Path(__file__).resolve().parents[2]

PROGRAMS_DIR = BASE_DIR / "data" / "parsed" / "programs"
RESULTS_DIR = BASE_DIR / "data" / "parsed" / "results"

OUTPUT_DIR = BASE_DIR / "data" / "matched"

OUTPUT_FILE = OUTPUT_DIR / "matched_races.json"


# ==================================================
# NORMALIZATION
# ==================================================

def normalize_text(value):
    """
    Normalize text so different representations
    can be compared safely.
    """

    if value is None:
        return None

    value = str(value).strip().upper()

    if not value:
        return None

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

    # Remove punctuation
    value = re.sub(
        r"[^A-Z0-9\s]",
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


def normalize_track_name(track):
    """
    Convert different track names into a common
    standard representation.
    """

    track = normalize_text(track)

    if not track:
        return None

    aliases = {

        # ------------------------------------------
        # PARIS VINCENNES
        # ------------------------------------------

        "PARIS VINCENNES": "PARIS VINCENNES",

        "PARIS VINCENNES NOCTURNE":
            "PARIS VINCENNES",

        "VINCENNES":
            "PARIS VINCENNES",

        "VINCENNES NOCTURNE":
            "PARIS VINCENNES",

        # ------------------------------------------
        # PARIS LONGCHAMP
        # ------------------------------------------

        "PARISLONGCHAMP":
            "PARIS LONGCHAMP",

        "PARIS LONGCHAMP":
            "PARIS LONGCHAMP",

        "LONGCHAMP":
            "PARIS LONGCHAMP",

        # ------------------------------------------
        # OTHER TRACKS
        # ------------------------------------------

        "AUTEUIL":
            "AUTEUIL",

        "CRAON":
            "CRAON",

        "LA CAPELLE":
            "LA CAPELLE",

        "LACAPELLE":
            "LA CAPELLE",

    }

    return aliases.get(
        track,
        track
    )


# ==================================================
# DATE NORMALIZATION
# ==================================================

def normalize_date(value):
    """
    Normalize dates into YYYY-MM-DD where possible.
    """

    if not value:
        return None

    value = str(value).strip()

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
                date_format
            ).strftime(
                "%Y-%m-%d"
            )

        except ValueError:

            pass

    return value


# ==================================================
# LOAD JSON FILES
# ==================================================

def load_json_files(folder):
    """
    Load all JSON files from a directory.
    """

    items = []

    if not folder.exists():

        print(
            f"Folder not found: {folder}"
        )

        return items

    for file_path in folder.glob("*.json"):

        try:

            with open(
                file_path,
                "r",
                encoding="utf-8"
            ) as file:

                data = json.load(file)

            if not isinstance(
                data,
                dict
            ):

                print(
                    f"Skipping invalid JSON structure: "
                    f"{file_path.name}"
                )

                continue

            data["_source_file"] = (
                file_path.name
            )

            items.append(
                data
            )

        except Exception as error:

            print(
                f"Error reading "
                f"{file_path.name}: "
                f"{error}"
            )

    return items


# ==================================================
# HELPER FUNCTIONS
# ==================================================

def get_program_info(program):
    """
    Extract normalized program information.
    """

    race = program.get(
        "race",
        {}
    )

    date = normalize_date(
        program.get("date")
    )

    track = normalize_track_name(
        race.get("track")
    )

    race_number = race.get(
        "race_number"
    )

    return {
        "date": date,
        "track": track,
        "race_number": race_number
    }


def get_result_info(result):
    """
    Extract normalized result information.
    """

    date = normalize_date(
        result.get("date")
    )

    track = normalize_track_name(
        result.get("track")
    )

    return {
        "date": date,
        "track": track
    }


def get_race_number(value):
    """
    Safely normalize race number.
    """

    if value is None:
        return None

    try:

        return int(value)

    except (
        ValueError,
        TypeError
    ):

        return value


# ==================================================
# REMOVE DUPLICATES
# ==================================================

def get_unique_programs(programs):
    """
    Keep one unique program for each:

    date + track + race number
    """

    unique = {}

    for program in programs:

        info = get_program_info(
            program
        )

        key = (

            info["date"],

            info["track"],

            get_race_number(
                info["race_number"]
            )

        )

        unique[key] = program

    return unique


def get_unique_results(results):
    """
    Keep one unique result meeting for each:

    date + track
    """

    unique = {}

    for result in results:

        info = get_result_info(
            result
        )

        key = (

            info["date"],

            info["track"]

        )

        unique[key] = result

    return unique


# ==================================================
# RESULT RACE LOOKUP
# ==================================================

def find_race_in_result(
    result,
    race_number
):
    """
    Find a specific race inside a result meeting.
    """

    target_race_number = (
        get_race_number(
            race_number
        )
    )

    for race in result.get(
        "races",
        []
    ):

        result_race_number = (
            get_race_number(
                race.get(
                    "race_number"
                )
            )
        )

        if (
            result_race_number
            == target_race_number
        ):

            return race

    return None


# ==================================================
# MATCH CANDIDATES
# ==================================================

def find_exact_result(
    results,
    date,
    track
):
    """
    Match using exact date and track.
    """

    candidates = []

    for result in results:

        info = get_result_info(
            result
        )

        if (
            info["date"] == date
            and info["track"] == track
        ):

            candidates.append(
                result
            )

    return candidates


def find_track_candidates(
    results,
    track
):
    """
    Find all result meetings
    with the same track.
    """

    candidates = []

    if not track:

        return candidates

    for result in results:

        info = get_result_info(
            result
        )

        if info["track"] == track:

            candidates.append(
                result
            )

    return candidates


def find_date_candidates(
    results,
    date
):
    """
    Find all result meetings
    on the same date.
    """

    candidates = []

    if not date:

        return candidates

    for result in results:

        info = get_result_info(
            result
        )

        if info["date"] == date:

            candidates.append(
                result
            )

    return candidates


# ==================================================
# SMART MATCHING
# ==================================================

def match_single_program(
    program,
    results
):
    """
    Match one program to a result.

    Matching priority:

    1. Exact date + track + race number
    2. Same track + race number
       when only one safe candidate exists
    3. Same date + race number
       when track is missing
    4. No unsafe guessing
    """

    program_info = (
        get_program_info(
            program
        )
    )

    date = (
        program_info["date"]
    )

    track = (
        program_info["track"]
    )

    race_number = (
        get_race_number(
            program_info["race_number"]
        )
    )

    # ==============================================
    # STRATEGY 1
    #
    # EXACT DATE + TRACK
    # ==============================================

    exact_candidates = (
        find_exact_result(
            results,
            date,
            track
        )
    )

    exact_matches = []

    for result in exact_candidates:

        matching_race = (
            find_race_in_result(
                result,
                race_number
            )
        )

        if matching_race:

            exact_matches.append(
                (
                    result,
                    matching_race
                )
            )

    if len(exact_matches) == 1:

        result, matching_race = (
            exact_matches[0]
        )

        return {

            "status":
                "matched",

            "strategy":
                "exact_date_track",

            "result":
                result,

            "race":
                matching_race,

            "candidates":
                []

        }

    # ==============================================
    # STRATEGY 2
    #
    # SAME TRACK + RACE NUMBER
    # ==============================================

    track_candidates = (
        find_track_candidates(
            results,
            track
        )
    )

    track_matches = []

    for result in track_candidates:

        matching_race = (
            find_race_in_result(
                result,
                race_number
            )
        )

        if matching_race:

            track_matches.append(
                (
                    result,
                    matching_race
                )
            )

    if len(track_matches) == 1:

        result, matching_race = (
            track_matches[0]
        )

        return {

            "status":
                "matched",

            "strategy":
                "track_race_fallback",

            "result":
                result,

            "race":
                matching_race,

            "candidates":
                []

        }

    # ==============================================
    # STRATEGY 3
    #
    # SAME DATE + RACE NUMBER
    #
    # Used when track is missing.
    # ==============================================

    if not track:

        date_candidates = (
            find_date_candidates(
                results,
                date
            )
        )

        date_matches = []

        for result in date_candidates:

            matching_race = (
                find_race_in_result(
                    result,
                    race_number
                )
            )

            if matching_race:

                date_matches.append(
                    (
                        result,
                        matching_race
                    )
                )

        if len(date_matches) == 1:

            result, matching_race = (
                date_matches[0]
            )

            return {

                "status":
                    "matched",

                "strategy":
                    "date_race_fallback",

                "result":
                    result,

                "race":
                    matching_race,

                "candidates":
                    []

            }

    # ==============================================
    # NO SAFE MATCH
    # ==============================================

    candidate_info = []

    for result in results:

        info = get_result_info(
            result
        )

        result_race = (
            find_race_in_result(
                result,
                race_number
            )
        )

        if result_race:

            candidate_info.append({

                "date":
                    info["date"],

                "track":
                    info["track"],

                "source":
                    result.get(
                        "_source_file"
                    )

            })

    return {

        "status":
            "unmatched",

        "strategy":
            None,

        "result":
            None,

        "race":
            None,

        "candidates":
            candidate_info

    }


# ==================================================
# MATCH ALL RACES
# ==================================================

def match_races(
    programs,
    results
):

    print(
        "\n" + "=" * 60
    )

    print(
        "MATCHING RACES"
    )

    print(
        "=" * 60
    )

    matched_races = []

    unmatched_programs = []

    unique_programs = (
        get_unique_programs(
            programs
        )
    )

    unique_results = (
        get_unique_results(
            results
        )
    )

    programs_to_match = list(
        unique_programs.values()
    )

    results_to_match = list(
        unique_results.values()
    )

    print(
        f"\nUnique programs: "
        f"{len(programs_to_match)}"
    )

    print(
        f"Unique results: "
        f"{len(results_to_match)}"
    )

    for program in programs_to_match:

        info = get_program_info(
            program
        )

        date = info["date"]

        track = info["track"]

        race_number = (
            get_race_number(
                info["race_number"]
            )
        )

        match = (
            match_single_program(
                program,
                results_to_match
            )
        )

        # ==========================================
        # SUCCESS
        # ==========================================

        if (
            match["status"]
            == "matched"
        ):

            result = (
                match["result"]
            )

            matching_race = (
                match["race"]
            )

            matched_race = {

                "date":
                    date,

                "track":
                    track,

                "race_number":
                    race_number,

                "match_strategy":
                    match["strategy"],

                "program":
                    program,

                "result":
                    matching_race,

                "arrival":
                    matching_race.get(
                        "arrival"
                    ),

                "program_source":
                    program.get(
                        "_source_file"
                    ),

                "result_source":
                    result.get(
                        "_source_file"
                    )

            }

            matched_races.append(
                matched_race
            )

            print(
                f"\nMATCHED "
                f"[{match['strategy']}]: "
                f"{date} | "
                f"{track} | "
                f"Race {race_number}"
            )

        # ==========================================
        # FAILURE
        # ==========================================

        else:

            unmatched_program = {

                "program":
                    program,

                "date":
                    date,

                "track":
                    track,

                "race_number":
                    race_number,

                "possible_candidates":
                    match["candidates"]

            }

            unmatched_programs.append(
                unmatched_program
            )

            print(
                f"\nNO SAFE MATCH: "
                f"{date} | "
                f"{track} | "
                f"Race {race_number}"
            )

            if match["candidates"]:

                print(
                    "Possible result candidates:"
                )

                for candidate in (
                    match["candidates"]
                ):

                    print(
                        f"  - "
                        f"{candidate['date']} | "
                        f"{candidate['track']} | "
                        f"{candidate['source']}"
                    )

    return (
        matched_races,
        unmatched_programs
    )


# ==================================================
# SAVE RESULTS
# ==================================================

def save_matches(
    matched_races,
    unmatched_programs
):

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    output = {

        "matched_races":
            matched_races,

        "unmatched_programs":
            unmatched_programs,

        "summary": {

            "matched_count":
                len(
                    matched_races
                ),

            "unmatched_count":
                len(
                    unmatched_programs
                )

        }

    }

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            output,
            file,
            indent=4,
            ensure_ascii=False
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
        f"\nMatched races: "
        f"{len(matched_races)}"
    )

    print(
        f"Unmatched programs: "
        f"{len(unmatched_programs)}"
    )

    print(
        f"\nSaved:\n"
        f"{OUTPUT_FILE}"
    )


# ==================================================
# MAIN FUNCTION
# ==================================================

def run_race_matching():

    print(
        "\n" + "=" * 60
    )

    print(
        "HORSE RACING MACHINE"
    )

    print(
        "RACE MATCHING ENGINE"
    )

    print(
        "=" * 60
    )

    programs = (
        load_json_files(
            PROGRAMS_DIR
        )
    )

    results = (
        load_json_files(
            RESULTS_DIR
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

    matched_races, unmatched_programs = (
        match_races(
            programs,
            results
        )
    )

    save_matches(
        matched_races,
        unmatched_programs
    )

    return matched_races
