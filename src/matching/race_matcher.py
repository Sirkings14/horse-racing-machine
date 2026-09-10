import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path


def normalize_text(value):
    """Normalize text for reliable comparisons."""
    if not value:
        return ""

    value = str(value).upper().strip()

    # Remove accents
    value = unicodedata.normalize("NFD", value)
    value = "".join(
        char for char in value
        if unicodedata.category(char) != "Mn"
    )

    # Normalize separators
    value = value.replace("-", " ")
    value = value.replace("_", " ")

    # Remove special characters
    value = re.sub(r"[^A-Z0-9 ]", " ", value)

    # Collapse spaces
    value = re.sub(r"\s+", " ", value).strip()

    return value


def normalize_track(track):
    """Normalize track names and common variations."""
    track = normalize_text(track)

    if not track:
        return ""

    aliases = {
        "PARIS VINCENNES NOCTURNE": "PARIS VINCENNES",
        "VINCENNES NOCTURNE": "PARIS VINCENNES",
        "VINCENNES": "PARIS VINCENNES",

        "PARIS LONGCHAMP": "PARISLONGCHAMP",
        "LONGCHAMP": "PARISLONGCHAMP",

        "AUTEUIL": "AUTEUIL",
        "CRAON": "CRAON",
        "LA CAPELLE": "LA CAPELLE",
    }

    return aliases.get(track, track)


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
            return datetime.strptime(value, date_format).strftime("%Y-%m-%d")
        except ValueError:
            pass

    return value


def get_race_number(race):
    """Extract race number safely."""
    for key in ["race_number", "race", "number"]:
        value = race.get(key)

        if value is not None:
            match = re.search(r"\d+", str(value))

            if match:
                return int(match.group())

    return None


def get_horse_names(race):
    """Extract normalized horse names."""
    horses = race.get("horses", [])

    names = set()

    for horse in horses:
        if isinstance(horse, dict):
            name = (
                horse.get("name")
                or horse.get("horse")
                or horse.get("horse_name")
            )

            if name:
                names.add(normalize_text(name))

        elif isinstance(horse, str):
            names.add(normalize_text(horse))

    return names


def calculate_match(program_race, result_race):
    """Calculate confidence score between program and result."""

    program_date = normalize_date(program_race.get("date"))
    result_date = normalize_date(result_race.get("date"))

    program_track = normalize_track(
        program_race.get("track")
    )

    result_track = normalize_track(
        result_race.get("track")
    )

    program_number = get_race_number(program_race)
    result_number = get_race_number(result_race)

    score = 0
    max_score = 0
    reasons = []

    # DATE
    if program_date and result_date:
        max_score += 40

        if program_date == result_date:
            score += 40
            reasons.append("date exact")

    # TRACK
    if program_track and result_track:
        max_score += 30

        if program_track == result_track:
            score += 30
            reasons.append("track exact")

    # RACE NUMBER
    if (
        program_number is not None
        and result_number is not None
    ):
        max_score += 20

        if program_number == result_number:
            score += 20
            reasons.append("race number exact")

    # HORSE OVERLAP
    program_horses = get_horse_names(program_race)
    result_horses = get_horse_names(result_race)

    if program_horses and result_horses:
        max_score += 10

        overlap = (
            len(program_horses & result_horses)
            / min(
                len(program_horses),
                len(result_horses)
            )
        )

        horse_score = round(overlap * 10)
        score += horse_score

        if horse_score:
            reasons.append(
                f"horse overlap {overlap:.0%}"
            )

    confidence = 0

    if max_score > 0:
        confidence = round(
            (score / max_score) * 100,
            2
        )

    return {
        "score": score,
        "max_score": max_score,
        "confidence": confidence,
        "reasons": reasons,
    }


def load_json_files(folder):
    """Load all JSON files from folder."""
    folder = Path(folder)

    records = []

    for path in folder.glob("*.json"):
        try:
            with open(path, "r", encoding="utf-8") as file:
                data = json.load(file)

            if isinstance(data, list):
                records.extend(data)

            elif isinstance(data, dict):
                records.append(data)

        except Exception as error:
            print(f"Failed loading {path.name}: {error}")

    return records


def deduplicate_races(races):
    """Remove duplicate parsed races."""

    unique = {}
    result = []

    for race in races:

        key = (
            normalize_date(race.get("date")),
            normalize_track(race.get("track")),
            get_race_number(race),
        )

        # If exact key is incomplete,
        # keep it because missing data may differ.
        if not all(key):
            result.append(race)
            continue

        if key not in unique:
            unique[key] = race
            result.append(race)

    return result


def classify_unmatched(program_race):
    """Classify unmatched races."""

    race_date = normalize_date(
        program_race.get("date")
    )

    if race_date:
        try:
            race_datetime = datetime.strptime(
                race_date,
                "%Y-%m-%d"
            )

            if race_datetime.date() > datetime.now().date():
                return "FUTURE_RACE"

        except ValueError:
            pass

    if not program_race.get("track"):
        return "PARSER_DATA_MISSING"

    return "RESULT_NOT_FOUND"


def match_races(
    programs,
    results,
    threshold=75,
):
    """Match program races against result races."""

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
                best_match is None
                or match_info["confidence"]
                > best_match["confidence"]
            ):
                best_match = match_info
                best_result = result

        if (
            best_match
            and best_match["confidence"] >= threshold
        ):

            matched.append({
                "program": program,
                "result": best_result,
                "match": best_match,
            })

            print(
                f"MATCHED "
                f"{normalize_date(program.get('date'))} | "
                f"{program.get('track')} | "
                f"Race {get_race_number(program)} | "
                f"{best_match['confidence']}%"
            )

        else:

            status = classify_unmatched(program)

            unmatched.append({
                "program": program,
                "status": status,
                "best_candidate": (
                    {
                        "result": best_result,
                        "match": best_match,
                    }
                    if best_result
                    else None
                ),
            })

            confidence = (
                best_match["confidence"]
                if best_match
                else 0
            )

            print(
                f"UNMATCHED [{status}] "
                f"{normalize_date(program.get('date'))} | "
                f"{program.get('track')} | "
                f"Race {get_race_number(program)} | "
                f"Best confidence: {confidence}%"
            )

    return matched, unmatched


def run_matching(
    programs_path="data/parsed/programs",
    results_path="data/parsed/results",
    output_path="data/matched/matched_races.json",
    review_path="data/matched/match_review.json",
):
    """Run complete race matching engine."""

    print("\n" + "=" * 60)
    print("HORSE RACING MACHINE")
    print("SMART RACE MATCHING ENGINE")
    print("=" * 60)

    programs = load_json_files(programs_path)
    results = load_json_files(results_path)

    print(f"\nPrograms loaded: {len(programs)}")
    print(f"Results loaded: {len(results)}")

    programs = deduplicate_races(programs)
    results = deduplicate_races(results)

    print(f"Unique programs: {len(programs)}")
    print(f"Unique results: {len(results)}")

    print("\nMATCHING RACES")
    print("=" * 60)

    matched, unmatched = match_races(
        programs,
        results,
        threshold=75,
    )

    Path(output_path).parent.mkdir(
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

    print("\n" + "=" * 60)
    print("RACE MATCHING COMPLETE")
    print("=" * 60)
    print(f"Matched races: {len(matched)}")
    print(f"Unmatched programs: {len(unmatched)}")
    print(f"Saved: {output_path}")
    print(f"Review: {review_path}")

    return matched, unmatched


if __name__ == "__main__":
    run_matching()
