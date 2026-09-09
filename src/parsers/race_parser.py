from pathlib import Path
from datetime import datetime
import json
import re


PROGRAMS_INPUT = Path("data/processed/programs")
RESULTS_INPUT = Path("data/processed/results")

PROGRAMS_OUTPUT = Path("data/structured/programs")
RESULTS_OUTPUT = Path("data/structured/results")


def ensure_directory(path):
    """
    Ensure a directory exists.
    """

    if path.exists() and not path.is_dir():
        raise RuntimeError(
            f"Expected directory but found file: {path}"
        )

    path.mkdir(
        parents=True,
        exist_ok=True
    )


def clean_text(text):
    """
    Clean extracted PDF text.
    """

    text = text.replace("\u202f", " ")
    text = text.replace("\u00a0", " ")

    return text


def extract_date_from_program(text):
    """
    Extract the race date from a program.
    """

    pattern = (
        r'DU\s+(LUNDI|MARDI|MERCREDI|JEUDI|'
        r'VENDREDI|SAMEDI|DIMANCHE)\s+'
        r'(\d{1,2})\s+'
        r'(JANVIER|FEVRIER|FÉVRIER|MARS|AVRIL|MAI|JUIN|'
        r'JUILLET|AOUT|AOÛT|SEPTEMBRE|OCTOBRE|NOVEMBRE|DECEMBRE|DÉCEMBRE)'
        r'\s+(\d{4})'
    )

    match = re.search(
        pattern,
        text,
        re.IGNORECASE
    )

    if not match:
        return None

    day = int(match.group(2))
    month_name = match.group(3).upper()
    year = int(match.group(4))

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
        "DÉCEMBRE": 12
    }

    month = months.get(month_name)

    if not month:
        return None

    return f"{year:04d}-{month:02d}-{day:02d}"


def extract_program_header(text):
    """
    Extract basic race information.
    """

    header = {
        "race_name": None,
        "track": None,
        "race_number": None,
        "race_type": None,
        "runners_count": None,
        "distance": None,
        "prize_euros": None
    }

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    for line in lines:

        upper = line.upper()

        if (
            "CONCURRENTS" in upper
            and "COURSE" in upper
        ):

            match = re.search(
                r'(\d+)\s+CONCURRENTS'
                r'.*?(\d+)(?:ER|ÈME|EME|E)\s+COURSE'
                r'.*?-\s*([A-ZÉÈÊÀÂÇÎÔÙÛÜ\s\-]+)'
                r'(\d[\d\s]*)\s*EUROS'
                r'.*?(\d[\d\s]*)\s*METRES',
                upper
            )

            if match:

                header["runners_count"] = int(
                    match.group(1)
                )

                header["race_number"] = int(
                    match.group(2)
                )

                header["race_type"] = (
                    match.group(3)
                    .strip()
                )

                header["prize_euros"] = int(
                    match.group(4)
                    .replace(" ", "")
                )

                header["distance"] = int(
                    match.group(5)
                    .replace(" ", "")
                )

        if (
            "PARIS-" in upper
            or "VINCENNES" in upper
            or "ENGHIEN" in upper
            or "DEAUVILLE" in upper
            or "CHANTILLY" in upper
            or "LONGCHAMP" in upper
        ):

            if "-" in upper:

                possible_track = (
                    upper.split("-")[0]
                    .strip()
                )

                if possible_track:
                    header["track"] = (
                        possible_track
                    )

    return header


def extract_favorites(text):
    """
    Extract favorite ranking.
    """

    match = re.search(
        r'FAVORIS\s*:\s*([0-9\s–\-]+)',
        text,
        re.IGNORECASE
    )

    if not match:
        return []

    numbers = re.findall(
        r'\d+',
        match.group(1)
    )

    return [
        int(number)
        for number in numbers
    ]


def extract_ranking(text, ranking_name):
    """
    Extract aptitude rankings such as
    FORME, CLASSE, PROGRES, REGULARITE.
    """

    pattern = (
        rf'{ranking_name}\s*:\s*'
        r'([0-9\s–\-]+)'
    )

    match = re.search(
        pattern,
        text,
        re.IGNORECASE
    )

    if not match:
        return []

    numbers = re.findall(
        r'\d+',
        match.group(1)
    )

    return [
        int(number)
        for number in numbers
    ]


def extract_program_arrival(text):
    """
    Extract previous published arrival
    if present in the program.
    """

    pattern = (
        r'ARRIVEE.*?:\s*'
        r'([0-9\s\-–]+)'
    )

    match = re.search(
        pattern,
        text,
        re.IGNORECASE
    )

    if not match:
        return []

    numbers = re.findall(
        r'\d+',
        match.group(1)
    )

    return [
        int(number)
        for number in numbers[:5]
    ]


def extract_horses(text):
    """
    Extract horses from the descriptive section.

    Current version extracts:
    - number
    - horse name
    - description

    More detailed runner-table parsing
    will be added later.
    """

    horses = []

    pattern = (
        r'(?m)^'
        r'(\d{1,2})\s*-\s*'
        r'([A-ZÀ-Ý\'\.\-\s]+?)'
        r'\s*:\s*'
        r'(.*?)(?='
        r'\n\d{1,2}\s*-\s*[A-ZÀ-Ý]'
        r'|\Z)'
    )

    matches = re.findall(
        pattern,
        text,
        re.DOTALL
    )

    for number, name, description in matches:

        cleaned_name = " ".join(
            name.split()
        )

        cleaned_description = (
            " ".join(
                description.split()
            )
        )

        horses.append(
            {
                "number": int(number),
                "horse": cleaned_name,
                "description": cleaned_description
            }
        )

    return horses


def parse_program_file(file_path):
    """
    Parse one processed program text file.
    """

    text = file_path.read_text(
        encoding="utf-8",
        errors="ignore"
    )

    text = clean_text(text)

    data = {
        "document_type": "program",
        "source_file": file_path.name,
        "parsed_at": (
            datetime.utcnow()
            .isoformat() + "Z"
        ),
        "date": extract_date_from_program(
            text
        ),
        "race": extract_program_header(
            text
        ),
        "horses": extract_horses(
            text
        ),
        "rankings": {
            "favorites": extract_favorites(
                text
            ),
            "form": extract_ranking(
                text,
                "FORME"
            ),
            "class": extract_ranking(
                text,
                "CLASSE"
            ),
            "progress": extract_ranking(
                text,
                "PROGRES"
            ),
            "regularity": extract_ranking(
                text,
                "REGULARITE"
            )
        },
        "published_arrival": extract_program_arrival(
            text
        )
    }

    return data


def extract_result_date(text):
    """
    Extract date from result document.
    """

    pattern = (
        r'DU\s*:\s*'
        r'(\d{1,2})\s*-\s*'
        r'(\d{1,2})\s*-\s*'
        r'(\d{4})'
    )

    match = re.search(
        pattern,
        text,
        re.IGNORECASE
    )

    if not match:
        return None

    day = int(match.group(1))
    month = int(match.group(2))
    year = int(match.group(3))

    return (
        f"{year:04d}-"
        f"{month:02d}-"
        f"{day:02d}"
    )


def extract_meeting(text):
    """
    Extract meeting number.
    """

    match = re.search(
        r'REUNION\s*-\s*(\d+)',
        text,
        re.IGNORECASE
    )

    if not match:
        return None

    return int(
        match.group(1)
    )


def extract_track(text):
    """
    Extract track name.
    """

    match = re.search(
        r'\(\s*([A-ZÀ-Ý\-]+)\s*\)',
        text
    )

    if not match:
        return None

    return (
        match.group(1)
        .strip()
    )


def extract_result_races(text):
    """
    Extract race arrivals.

    Looks for patterns such as:

    1ère
    3 - 9 - 8

    2ième
    6 - 10 - 11
    """

    races = {}

    pattern = (
        r'(\d+)(?:ère|ieme|ième|ème|e)'
        r'\s+'
        r'([0-9\s\-–]+)'
    )

    matches = re.findall(
        pattern,
        text,
        re.IGNORECASE
    )

    for race_number, arrival_text in matches:

        numbers = re.findall(
            r'\d+',
            arrival_text
        )

        if numbers:

            races[str(
                int(race_number)
            )] = [
                int(number)
                for number in numbers[:5]
            ]

    return races


def parse_result_file(file_path):
    """
    Parse one processed result text file.
    """

    text = file_path.read_text(
        encoding="utf-8",
        errors="ignore"
    )

    text = clean_text(text)

    data = {
        "document_type": "result",
        "source_file": file_path.name,
        "parsed_at": (
            datetime.utcnow()
            .isoformat() + "Z"
        ),
        "date": extract_result_date(
            text
        ),
        "meeting": extract_meeting(
            text
        ),
        "track": extract_track(
            text
        ),
        "races": extract_result_races(
            text
        )
    }

    return data


def save_json(data, output_path):
    """
    Save parsed data as JSON.
    """

    output_path.write_text(
        json.dumps(
            data,
            indent=4,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )


def process_programs():
    """
    Parse all program text files.
    """

    ensure_directory(
        PROGRAMS_OUTPUT
    )

    files = sorted(
        PROGRAMS_INPUT.glob("*.txt")
    )

    print("\n" + "=" * 60)
    print("PARSING PROGRAM FILES")
    print("=" * 60)

    print(
        f"Program files found: {len(files)}"
    )

    success = 0
    failed = 0

    for file_path in files:

        try:

            data = parse_program_file(
                file_path
            )

            output_path = (
                PROGRAMS_OUTPUT /
                f"{file_path.stem}.json"
            )

            save_json(
                data,
                output_path
            )

            print(
                f"Parsed program: "
                f"{file_path.name}"
            )

            success += 1

        except Exception as error:

            print(
                f"Program parsing failed "
                f"for {file_path.name}: "
                f"{error}"
            )

            failed += 1

    return success, failed


def process_results():
    """
    Parse all result text files.
    """

    ensure_directory(
        RESULTS_OUTPUT
    )

    files = sorted(
        RESULTS_INPUT.glob("*.txt")
    )

    print("\n" + "=" * 60)
    print("PARSING RESULT FILES")
    print("=" * 60)

    print(
        f"Result files found: {len(files)}"
    )

    success = 0
    failed = 0

    for file_path in files:

        try:

            data = parse_result_file(
                file_path
            )

            output_path = (
                RESULTS_OUTPUT /
                f"{file_path.stem}.json"
            )

            save_json(
                data,
                output_path
            )

            print(
                f"Parsed result: "
                f"{file_path.name}"
            )

            success += 1

        except Exception as error:

            print(
                f"Result parsing failed "
                f"for {file_path.name}: "
                f"{error}"
            )

            failed += 1

    return success, failed


def parse_all_files():
    """
    Parse all processed program
    and result files.
    """

    print("\n" + "=" * 60)
    print("HORSE RACING MACHINE")
    print("RACE DATA PARSER")
    print("=" * 60)

    program_success, program_failed = (
        process_programs()
    )

    result_success, result_failed = (
        process_results()
    )

    print("\n" + "=" * 60)
    print("PARSING COMPLETE")
    print("=" * 60)

    print(
        f"Programs parsed: "
        f"{program_success}"
    )

    print(
        f"Program failures: "
        f"{program_failed}"
    )

    print(
        f"Results parsed: "
        f"{result_success}"
    )

    print(
        f"Result failures: "
        f"{result_failed}"
    )

    print("=" * 60)


if __name__ == "__main__":
    parse_all_files()
