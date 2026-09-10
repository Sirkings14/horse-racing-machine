import json
import re
import unicodedata
from pathlib import Path


# --------------------------------------------------
# PATHS
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parents[2]

PROGRAMS_DIR = BASE_DIR / "data" / "parsed" / "programs"
RESULTS_DIR = BASE_DIR / "data" / "parsed" / "results"
OUTPUT_DIR = BASE_DIR / "data" / "matched"

OUTPUT_FILE = OUTPUT_DIR / "matched_races.json"


# --------------------------------------------------
# NORMALIZATION
# --------------------------------------------------

def normalize_text(value):
    """
    Normalize text for reliable comparisons.
    """

    if not value:
        return None

    value = str(value).strip().upper()

    # Remove accents
    value = unicodedata.normalize("NFD", value)

    value = "".join(
        char
        for char in value
        if unicodedata.category(char) != "Mn"
    )

    # Normalize separators
    value = value.replace("-", " ")
    value = value.replace("_", " ")

    # Remove unnecessary punctuation
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
    Convert different representations of the same
    racecourse into one standard name.
    """

    track = normalize_text(track)

    if not track:
        return None

    # --------------------------------------------------
    # KNOWN TRACK ALIASES
    # --------------------------------------------------

    aliases = {

        # Vincennes
        "PARIS VINCENNES NOCTURNE": "PARIS VINCENNES",
        "VINCENNES NOCTURNE": "PARIS VINCENNES",
        "PARIS VINCENNES": "PARIS VINCENNES",
        "VINCENNES": "PARIS VINCENNES",

        # Longchamp
        "PARISLONGCHAMP": "PARIS LONGCHAMP",
        "PARIS LONGCHAMP": "PARIS LONGCHAMP",
        "LONGCHAMP": "PARIS LONGCHAMP",

        # La Capelle
        "LA CAPELLE": "LA CAPELLE",

        # Craon
        "CRAON": "CRAON",

        # Auteuil
        "AUTEUIL": "AUTEUIL",
    }

    if track in aliases:
        return aliases[track]

    return track


# --------------------------------------------------
# FILE LOADING
# --------------------------------------------------

def load_json_files(folder):
    """
    Load every JSON file inside a folder.
    """

    items = []

    if not folder.exists():

        print(
            f"Folder not found: {folder}"
        )

        return items

    for file_path in sorted(
        folder.glob("*.json")
    ):

        try:

            with open(
                file_path,
                "r",
                encoding="utf-8"
            ) as file:

                data = json.load(file)

            data["_source_file"] = (
                file_path.name
            )

            items.append(data)

        except Exception as error:

            print(
                f"Error reading "
                f"{file_path.name}: "
                f"{error}"
            )

    return items


# --------------------------------------------------
# REMOVE DUPLICATES
# --------------------------------------------------

def get_unique_programs(programs):
    """
    Keep one program per:

    date + normalized track + race number.
    """

    unique = {}

    for program in programs:

        date = program.get("date")

        race = program.get(
            "race",
            {}
        )

        track = normalize_track_name(
            race.get("track")
        )

        race_number = race.get(
            "race_number"
        )

        key = (
            date,
            track,
            race_number
        )

        # Keep newest version encountered
        unique[key] = program

    return unique


def get_unique_results(results):
    """
    Keep one result per:

    date + normalized track.

    Result files may contain multiple races.
    """

    unique = {}

    for result in results:

        date = result.get("date")

        track = normalize_track_name(
            result.get("track")
        )

        key = (
            date,
            track
        )

        unique[key] = result

    return unique


# --------------------------------------------------
# DIAGNOSTICS
# --------------------------------------------------

def get_result_race_numbers(result):
    """
    Return all race numbers available
    inside a result meeting.
    """

    return [

        race.get("race_number")

        for race in result.get(
            "races",
            []
        )

    ]


def print_available_results(unique_results):
    """
    Print all unique result meetings.

    This lets us inspect exactly what
    the result parser extracted.
    """

    print("\n" + "=" * 60)
    print("AVAILABLE RESULT MEETINGS")
    print("=" * 60)

    for (
        date,
        track
    ), result in sorted(
        unique_results.items(),
        key=lambda item: (
            str(item[0][0]),
            str(item[0][1])
        )
    ):

        races = get_result_race_numbers(
            result
        )

        print(
            f"{date} | "
            f"{track} | "
            f"Races: {races} | "
            f"Source: "
            f"{result.get('_source_file')}"
        )


def print_same_date_candidates(
    date,
    unique_results
):
    """
    Print all result meetings available
    on the same date.
    """

    candidates = []

    for (
        result_date,
        result_track
    ), result in unique_results.items():

        if result_date == date:

            candidates.append(
                (
                    result_track,
                    get_result_race_numbers(
                        result
                    ),
                    result.get(
                        "_source_file"
                    )
                )
            )

    if not candidates:

        print(
            "  No result meeting "
            "found on this date."
        )

        return

    print(
        "  Same-date result candidates:"
    )

    for (
        track,
        races,
        source
    ) in candidates:

        print(
            f"  -> Track: "
            f"{track} | "
            f"Races: {races} | "
            f"Source: {source}"
        )


# --------------------------------------------------
# MATCHING
# --------------------------------------------------

def match_races(
    programs,
    results
):

    print("\n" + "=" * 60)
    print("MATCHING RACES")
    print("=" * 60)

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

    print(
        f"\nUnique programs: "
        f"{len(unique_programs)}"
    )

    print(
        f"Unique results: "
        f"{len(unique_results)}"
    )

    # --------------------------------------------------
    # SHOW AVAILABLE RESULTS
    # --------------------------------------------------

    print_available_results(
        unique_results
    )

    # --------------------------------------------------
    # BUILD RESULT LOOKUP
    # --------------------------------------------------

    result_lookup = {}

    for (
        date,
        track
    ), result in unique_results.items():

        result_lookup[
            (date, track)
        ] = result

    # --------------------------------------------------
    # MATCH EACH PROGRAM
    # --------------------------------------------------

    for key, program in sorted(
        unique_programs.items(),
        key=lambda item: (
            str(item[0][0]),
            str(item[0][1]),
            str(item[0][2])
        )
    ):

        (
            date,
            normalized_track,
            race_number
        ) = key

        original_track = (
            program
            .get("race", {})
            .get("track")
        )

        print(
            f"\nCHECKING: "
            f"{date} | "
            f"{original_track} | "
            f"Race {race_number}"
        )

        print(
            f"Normalized track: "
            f"{normalized_track}"
        )

        # ----------------------------------------------
        # NORMAL MATCH
        # ----------------------------------------------

        result = result_lookup.get(
            (
                date,
                normalized_track
            )
        )

        # ----------------------------------------------
        # FALLBACK:
        # MISSING TRACK
        # ----------------------------------------------

        if result is None:

            same_date_results = [

                item

                for (
                    result_date,
                    result_track
                ), item

                in result_lookup.items()

                if result_date == date

            ]

            if (
                normalized_track is None
                and len(same_date_results) == 1
            ):

                result = (
                    same_date_results[0]
                )

                print(
                    "FALLBACK MATCH "
                    "(missing track)"
                )

        # ----------------------------------------------
        # NO RESULT MEETING FOUND
        # ----------------------------------------------

        if result is None:

            print(
                f"NO MATCH: "
                f"{date} | "
                f"{original_track} | "
                f"Race {race_number}"
            )

            print_same_date_candidates(
                date,
                unique_results
            )

            unmatched_programs.append(
                program
            )

            continue

        # ----------------------------------------------
        # RESULT MEETING FOUND
        # ----------------------------------------------

        print(
            "Result meeting found:"
        )

        print(
            f"  Date: "
            f"{result.get('date')}"
        )

        print(
            f"  Track: "
            f"{result.get('track')}"
        )

        print(
            f"  Available races: "
            f"{get_result_race_numbers(result)}"
        )

        # ----------------------------------------------
        # FIND RACE INSIDE RESULT MEETING
        # ----------------------------------------------

        matching_race = None

        for result_race in result.get(
            "races",
            []
        ):

            if (
                result_race.get(
                    "race_number"
                )
                == race_number
            ):

                matching_race = (
                    result_race
                )

                break

        # ----------------------------------------------
        # RACE NUMBER NOT FOUND
        # ----------------------------------------------

        if matching_race is None:

            print(
                f"NO RACE RESULT: "
                f"{date} | "
                f"{normalized_track} | "
                f"Race {race_number}"
            )

            print(
                f"Available race numbers: "
                f"{get_result_race_numbers(result)}"
            )

            unmatched_programs.append(
                program
            )

            continue

        # ----------------------------------------------
        # SUCCESSFUL MATCH
        # ----------------------------------------------

        matched_race = {

            "date": date,

            "track": normalized_track,

            "race_number": race_number,

            "program": program,

            "result": matching_race,

            "arrival": matching_race.get(
                "arrival"
            )

        }

        matched_races.append(
            matched_race
        )

        print(
            f"MATCHED: "
            f"{date} | "
            f"{normalized_track} | "
            f"Race {race_number}"
        )

    return (
        matched_races,
        unmatched_programs
    )


# --------------------------------------------------
# SAVE
# --------------------------------------------------

def save_matches(
    matched_races,
    unmatched_programs
):

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    output = {

        "matched_races": (
            matched_races
        ),

        "unmatched_programs": (
            unmatched_programs
        ),

        "summary": {

            "matched_count": len(
                matched_races
            ),

            "unmatched_count": len(
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

    print("\n" + "=" * 60)
    print("RACE MATCHING COMPLETE")
    print("=" * 60)

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


# --------------------------------------------------
# MAIN
# --------------------------------------------------

def run_race_matching():

    print("\n" + "=" * 60)
    print("HORSE RACING MACHINE")
    print("RACE MATCHING ENGINE")
    print("=" * 60)

    programs = load_json_files(
        PROGRAMS_DIR
    )

    results = load_json_files(
        RESULTS_DIR
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


# --------------------------------------------------
# RUN DIRECTLY
# --------------------------------------------------

if __name__ == "__main__":

    run_race_matching()
