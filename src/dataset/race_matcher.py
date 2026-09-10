import json
from pathlib import Path


PROGRAMS_DIR = Path("data/structured/programs")
RESULTS_DIR = Path("data/structured/results")

OUTPUT_DIR = Path("data/matched")
OUTPUT_FILE = OUTPUT_DIR / "matched_races.json"


def load_json_files(folder):
    records = []

    for file_path in sorted(folder.glob("*.json")):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            data["_path"] = str(file_path)
            records.append(data)

        except Exception as e:
            print(f"Failed to load {file_path.name}: {e}")

    return records


def normalize_text(value):
    if not value:
        return ""

    return (
        str(value)
        .upper()
        .strip()
        .replace("É", "E")
        .replace("È", "E")
        .replace("Ê", "E")
        .replace("-", " ")
    )


def normalize_track(value):
    """
    Makes track names easier to compare.
    """

    value = normalize_text(value)

    replacements = {
        "PARIS VINCENNES NOCTURNE": "VINCENNES",
        "PARIS VINCENNES": "VINCENNES",
    }

    return replacements.get(value, value)


def deduplicate_programs(programs):
    unique = {}

    for program in programs:

        race = program.get("race", {})

        key = (
            program.get("date"),
            normalize_track(race.get("track")),
            race.get("race_number"),
        )

        if key not in unique:
            unique[key] = program

    return list(unique.values())


def deduplicate_results(results):
    unique = {}

    for result in results:

        key = (
            result.get("date"),
            normalize_track(result.get("track")),
        )

        if key not in unique:
            unique[key] = result

    return list(unique.values())


def get_result_race(result, race_number):
    """
    Finds the specific race inside a result document.
    """

    races = result.get("races", [])

    # Support both possible parser structures
    if isinstance(races, dict):

        race = races.get(str(race_number))

        if race:
            return {
                "race_number": race_number,
                "arrival": race
            }

        return None

    for race in races:

        if race.get("race_number") == race_number:
            return race

    return None


def find_matching_result(program, results):

    race = program.get("race", {})

    program_date = program.get("date")
    program_track = normalize_track(race.get("track"))
    program_race_number = race.get("race_number")

    if not program_date:
        return None

    if not program_track:
        return None

    if program_race_number is None:
        return None

    for result in results:

        result_date = result.get("date")
        result_track = normalize_track(result.get("track"))

        if result_date != program_date:
            continue

        if result_track != program_track:
            continue

        matched_race = get_result_race(
            result,
            program_race_number
        )

        if matched_race:

            return {
                "result_document": result,
                "race_result": matched_race
            }

    return None


def build_match(program, match):

    race = program.get("race", {})

    race_result = match["race_result"]

    arrival = race_result.get("arrival", [])

    return {
        "date": program.get("date"),

        "track": race.get("track"),

        "race_number": race.get("race_number"),

        "race_name": race.get("race_name"),

        "race_type": race.get("race_type"),

        "distance": race.get("distance"),

        "runners_count": race.get("runners_count"),

        "horses": program.get("horses", []),

        "rankings": program.get("rankings", {}),

        "actual_arrival": arrival,

        "source_program": program.get("source_file"),

        "source_result": match[
            "result_document"
        ].get("source_file")
    }


def match_races():

    print("\n" + "=" * 60)
    print("HORSE RACING MACHINE")
    print("RACE MATCHING ENGINE")
    print("=" * 60)

    programs = load_json_files(PROGRAMS_DIR)
    results = load_json_files(RESULTS_DIR)

    print(f"\nPrograms loaded: {len(programs)}")
    print(f"Results loaded: {len(results)}")

    programs = deduplicate_programs(programs)
    results = deduplicate_results(results)

    print(f"\nUnique programs: {len(programs)}")
    print(f"Unique results: {len(results)}")

    matched_races = []
    unmatched_programs = []

    print("\nMATCHING RACES")
    print("=" * 60)

    for program in programs:

        race = program.get("race", {})

        match = find_matching_result(
            program,
            results
        )

        if match:

            matched = build_match(
                program,
                match
            )

            matched_races.append(matched)

            print(
                f"MATCHED: "
                f"{program.get('date')} | "
                f"{race.get('track')} | "
                f"Race {race.get('race_number')}"
            )

        else:

            unmatched_programs.append(program)

            print(
                f"NO MATCH: "
                f"{program.get('date')} | "
                f"{race.get('track')} | "
                f"Race {race.get('race_number')}"
            )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            matched_races,
            f,
            indent=4,
            ensure_ascii=False
        )

    print("\n" + "=" * 60)
    print("RACE MATCHING COMPLETE")
    print("=" * 60)

    print(f"\nMatched races: {len(matched_races)}")
    print(f"Unmatched programs: {len(unmatched_programs)}")

    print(f"\nSaved:")
    print(OUTPUT_FILE)


if __name__ == "__main__":
    match_races()
