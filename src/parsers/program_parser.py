import json
import re
from datetime import datetime
from pathlib import Path


PROGRAMS_FOLDER = Path("data/processed/programs")
OUTPUT_FOLDER = Path("data/structured/programs")


def clean_text(text):
    """
    Clean extracted PDF text.
    """

    text = text.replace("\u202f", " ")
    text = text.replace("\xa0", " ")

    text = re.sub(
        r"[ \t]+",
        " ",
        text
    )

    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text
    )

    return text.strip()


def extract_date(text):
    """
    Extract race date.

    Example:
    DU VENDREDI 11 SEPTEMBRE 2026
    """

    pattern = (
        r"DU\s+(?:LUNDI|MARDI|MERCREDI|JEUDI|"
        r"VENDREDI|SAMEDI|DIMANCHE)\s+"
        r"(\d{1,2})\s+"
        r"(JANVIER|FEVRIER|FÉVRIER|MARS|AVRIL|MAI|JUIN|"
        r"JUILLET|AOUT|AOÛT|SEPTEMBRE|OCTOBRE|"
        r"NOVEMBRE|DECEMBRE|DÉCEMBRE)\s+"
        r"(\d{4})"
    )

    match = re.search(
        pattern,
        text,
        re.IGNORECASE
    )

    if not match:
        return None

    day = int(match.group(1))
    month_name = match.group(2).upper()
    year = int(match.group(3))

    months = {
        "JANVIER": 1,
        "FEVRIER": 2,
        "FÉVRIER": 2,
        "MARS": 3,
        "AVRIL": 4,
        "MAI": 5,
        "JUIN": 6,
        "JUILLET": 7,
        "AOUT": 8,
        "AOÛT": 8,
        "SEPTEMBRE": 9,
        "OCTOBRE": 10,
        "NOVEMBRE": 11,
        "DECEMBRE": 12,
        "DÉCEMBRE": 12,
    }

    month = months.get(month_name)

    if not month:
        return None

    try:
        date = datetime(
            year,
            month,
            day
        )

        return date.strftime(
            "%Y-%m-%d"
        )

    except ValueError:
        return None


def extract_race_info(text):
    """
    Extract race information.
    """

    race = {
        "race_name": None,
        "track": None,
        "race_number": None,
        "race_type": None,
        "runners_count": None,
        "distance": None,
        "prize_euros": None,
    }

    # -------------------------------------------------
    # TRACK + RACE NAME
    # -------------------------------------------------

    track_patterns = [
        (
            r"\n([A-ZÀ-Ü0-9'\-\s]+?)"
            r"\s*-\s*"
            r"(PRIX\s+[A-ZÀ-Ü0-9'\-\s]+)"
            r"\n"
        ),
        (
            r"^([A-ZÀ-Ü0-9'\-\s]+?)"
            r"\s*-\s*"
            r"(PRIX\s+[A-ZÀ-Ü0-9'\-\s]+)"
            r"$"
        ),
    ]

    for track_pattern in track_patterns:

        match = re.search(
            track_pattern,
            text,
            re.MULTILINE
        )

        if not match:
            continue

        track = match.group(1).strip()
        race_name = match.group(2).strip()

        if len(track) > 2:
            race["track"] = track

        race["race_name"] = race_name

        break

    # -------------------------------------------------
    # RUNNERS COUNT
    # -------------------------------------------------

    match = re.search(
        r"(\d+)\s+CONCURRENTS?",
        text,
        re.IGNORECASE
    )

    if match:
        race["runners_count"] = int(
            match.group(1)
        )

    # -------------------------------------------------
    # RACE NUMBER
    # -------------------------------------------------

    race_number_patterns = [
        r"(\d+)(?:ère|ere|ème|eme)\s+COURSE",
        r"(\d+)(?:ER|E|EME|ÈME)\s+COURSE",
    ]

    for pattern in race_number_patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:
            race["race_number"] = int(
                match.group(1)
            )
            break

    # -------------------------------------------------
    # RACE TYPE
    # -------------------------------------------------

    race_types = [
        "STEEPLE-CHASE",
        "ATTELE",
        "MONTÉ",
        "MONTE",
        "PLAT",
        "OBSTACLE",
        "HAIES",
    ]

    for race_type in race_types:

        if re.search(
            rf"\b{re.escape(race_type)}\b",
            text,
            re.IGNORECASE
        ):
            race["race_type"] = race_type
            break

    # -------------------------------------------------
    # PRIZE
    # -------------------------------------------------

    match = re.search(
        r"(\d[\d\s]*)\s+EUROS",
        text,
        re.IGNORECASE
    )

    if match:

        value = re.sub(
            r"\s+",
            "",
            match.group(1)
        )

        try:
            race["prize_euros"] = int(value)
        except ValueError:
            pass

    # -------------------------------------------------
    # DISTANCE
    # -------------------------------------------------

    match = re.search(
        r"(\d[\d\s]*)\s+METRES?",
        text,
        re.IGNORECASE
    )

    if match:

        value = re.sub(
            r"\s+",
            "",
            match.group(1)
        )

        try:
            race["distance"] = int(value)
        except ValueError:
            pass

    return race


def clean_horse_name(name):
    """
    Normalize a horse name.
    """

    name = name.strip()

    name = re.sub(
        r"\s+",
        " ",
        name
    )

    return name


def clean_description(description):
    """
    Normalize a horse description.
    """

    description = re.sub(
        r"\s+",
        " ",
        description
    ).strip()

    return description


def extract_horses(text, expected_runners=None):
    """
    Extract one horse record per horse number.

    Duplicate horse numbers are explicitly deduplicated.

    When a duplicate occurs, the version with the longer
    description is retained.
    """

    stop_markers = [
        "RESULTATS DES COURSES",
        "RÉSULTATS DES COURSES",
        "===== PAGE 2 =====",
        "JOURNAL HIPPIQUE",
        "CHEVAUX DRIVERS",
        "LES MEILLEURS DE LA SEMAINE",
        "PARIS TURF",
        "TIERCE MAGAZINE",
        "FAVORIS :",
        "FAVORIS:",
        "FORME :",
        "FORME:",
        "CLASSE :",
        "CLASSE:",
        "PROGRES :",
        "PROGRÈS :",
        "PROGRES:",
        "PROGRÈS:",
        "REGULARITE :",
        "RÉGULARITÉ :",
        "REGULARITE:",
        "RÉGULARITÉ:",
    ]

    # Only process the portion of the document before
    # the first strong stop marker.
    working_text = text

    marker_positions = []

    upper_text = text.upper()

    for marker in stop_markers:

        position = upper_text.find(
            marker.upper()
        )

        if position != -1:
            marker_positions.append(position)

    if marker_positions:
        working_text = text[
            :min(marker_positions)
        ]

    horse_pattern = (
        r"(?m)^\s*"
        r"(\d{1,2})\s*-\s*"
        r"([A-ZÀ-Ü][A-ZÀ-Ü0-9'\.\- ]+?)"
        r"\s*:\s*"
    )

    matches = list(
        re.finditer(
            horse_pattern,
            working_text
        )
    )

    horses_by_number = {}

    for index, match in enumerate(matches):

        number = int(
            match.group(1)
        )

        horse_name = clean_horse_name(
            match.group(2)
        )

        description_start = match.end()

        if index + 1 < len(matches):
            description_end = (
                matches[index + 1].start()
            )
        else:
            description_end = len(
                working_text
            )

        description = working_text[
            description_start:
            description_end
        ]

        description = clean_description(
            description
        )

        candidate = {
            "number": number,
            "horse": horse_name,
            "description": description,
        }

        # Deduplicate by horse number.
        existing = horses_by_number.get(
            number
        )

        if existing is None:
            horses_by_number[number] = candidate
            continue

        # Prefer the more informative entry.
        existing_score = (
            len(existing["horse"])
            + len(existing["description"])
        )

        candidate_score = (
            len(candidate["horse"])
            + len(candidate["description"])
        )

        if candidate_score > existing_score:
            horses_by_number[number] = candidate

    horses = list(
        horses_by_number.values()
    )

    horses.sort(
        key=lambda item: item["number"]
    )

    # If the program tells us the expected
    # number of runners, report a warning rather
    # than manufacturing missing horses.
    if (
        expected_runners is not None
        and len(horses) != expected_runners
    ):
        print(
            "WARNING: horse count mismatch: "
            f"expected {expected_runners}, "
            f"extracted {len(horses)}"
        )

    return horses


def extract_number_list(text, label):
    """
    Extract a ranking list from one line only.
    """

    pattern = (
        rf"{re.escape(label)}"
        r"\s*:\s*"
        r"([^\n\r]+)"
    )

    match = re.search(
        pattern,
        text,
        re.IGNORECASE
    )

    if not match:
        return []

    line = match.group(1)

    numbers = re.findall(
        r"\b\d{1,2}\b",
        line
    )

    return [
        int(number)
        for number in numbers
    ]


def extract_rankings(text):
    """
    Extract rankings.
    """

    return {
        "favorites": extract_number_list(
            text,
            "FAVORIS"
        ),

        "form": extract_number_list(
            text,
            "FORME"
        ),

        "class": extract_number_list(
            text,
            "CLASSE"
        ),

        "progress": extract_number_list(
            text,
            "PROGRES"
        ),

        "regularity": extract_number_list(
            text,
            "REGULARITE"
        ),
    }


def extract_published_arrival(text):
    """
    Extract previous published arrival.
    """

    pattern = (
        r'ARRIVEE\s+DU.*?'
        r":\s*"
        r"([0-9\s\-–]+)"
        r"(?:NPO|NP|$)"
    )

    match = re.search(
        pattern,
        text,
        re.IGNORECASE
    )

    if not match:
        return []

    numbers = re.findall(
        r"\d+",
        match.group(1)
    )

    return [
        int(number)
        for number in numbers
    ]


def parse_program_file(file_path):
    """
    Parse one processed program text file.
    """

    raw_text = file_path.read_text(
        encoding="utf-8"
    )

    text = clean_text(
        raw_text
    )

    race_info = extract_race_info(
        text
    )

    horses = extract_horses(
        text,
        expected_runners=race_info.get(
            "runners_count"
        )
    )

    return {
        "document_type": "program",

        "source_file": file_path.name,

        "parsed_at": (
            datetime.utcnow()
            .isoformat()
            + "Z"
        ),

        "date": extract_date(
            text
        ),

        "race": race_info,

        "horses": horses,

        "rankings": extract_rankings(
            text
        ),

        "published_arrival": (
            extract_published_arrival(
                text
            )
        ),
    }


def process_all_programs():

    OUTPUT_FOLDER.mkdir(
        parents=True,
        exist_ok=True
    )

    files = sorted(
        PROGRAMS_FOLDER.glob(
            "*.txt"
        )
    )

    print("\n" + "=" * 60)
    print("PARSING PROGRAM FILES")
    print("=" * 60)

    print(
        f"Program files found: "
        f"{len(files)}"
    )

    success_count = 0
    failed_count = 0

    for file_path in files:

        try:

            data = parse_program_file(
                file_path
            )

            output_path = (
                OUTPUT_FOLDER
                / f"{file_path.stem}.json"
            )

            output_path.write_text(
                json.dumps(
                    data,
                    ensure_ascii=False,
                    indent=4
                ),
                encoding="utf-8"
            )

            print(
                f"Parsed successfully: "
                f"{file_path.name}"
            )

            print(
                f"Horses extracted: "
                f"{len(data['horses'])}"
            )

            success_count += 1

        except Exception as error:

            print(
                f"Failed: "
                f"{file_path.name}"
            )

            print(
                f"Error: {error}"
            )

            failed_count += 1

    print("\n" + "=" * 60)

    print(
        f"Programs parsed: "
        f"{success_count}"
    )

    print(
        f"Failures: "
        f"{failed_count}"
    )

    print("=" * 60)


if __name__ == "__main__":
    process_all_programs()
