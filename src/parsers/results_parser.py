from pathlib import Path
from datetime import datetime
import json
import re


INPUT_FOLDER = Path("data/processed/results")
OUTPUT_FOLDER = Path("data/structured/results")


def extract_date(text):
    """
    Extract the race date.

    Example:
    DU :06 - 09 - 2026
    """

    pattern = (
        r"DU\s*:?\s*"
        r"(\d{2})\s*-\s*"
        r"(\d{2})\s*-\s*"
        r"(\d{4})"
    )

    match = re.search(
        pattern,
        text,
        re.IGNORECASE
    )

    if not match:
        return None

    day = match.group(1)
    month = match.group(2)
    year = match.group(3)

    return f"{year}-{month}-{day}"


def extract_meeting(text):
    """
    Extract meeting number.

    Example:
    REUNION - 5
    """

    match = re.search(
        r"REUNION\s*-?\s*(\d+)",
        text,
        re.IGNORECASE
    )

    if not match:
        return None

    return int(match.group(1))


def extract_track(text):
    """
    Extract track name.

    Example:
    ( VIRE )
    """

    match = re.search(
        r"\(\s*([A-ZÀ-Ÿ'\-\s]+?)\s*\)",
        text
    )

    if not match:
        return None

    track = match.group(1).strip()

    return track


def extract_race_arrivals(text):
    """
    Extract race arrivals.

    The result PDF structure usually contains:

    1ère 3 - 9 - 8
    2ième 6 - 10 - 11
    3ième 3 - 8 - 5

    We only extract the first three arrival numbers.

    Prize amounts and betting data are ignored.
    """

    races = []

    pattern = (
        r"(?P<label>"
        r"\d+(?:ère|ieme|ième|e)"
        r")"
        r"\s+"
        r"(?P<a>\d+)"
        r"\s*-\s*"
        r"(?P<b>\d+)"
        r"\s*-\s*"
        r"(?P<c>\d+)"
    )

    matches = re.finditer(
        pattern,
        text,
        re.IGNORECASE
    )

    race_number = 1

    for match in matches:

        first = int(
            match.group("a")
        )

        second = int(
            match.group("b")
        )

        third = int(
            match.group("c")
        )

        races.append(
            {
                "race_number": race_number,
                "arrival": [
                    first,
                    second,
                    third
                ],
                "winner": first,
                "second": second,
                "third": third
            }
        )

        race_number += 1

    return races


def parse_result_file(file_path):
    """
    Parse one processed result text file.
    """

    text = file_path.read_text(
        encoding="utf-8"
    )

    date = extract_date(text)

    meeting = extract_meeting(text)

    track = extract_track(text)

    races = extract_race_arrivals(
        text
    )

    return {
        "document_type": "result",

        "source_file":
            file_path.name,

        "parsed_at":
            datetime.utcnow()
            .isoformat() + "Z",

        "date":
            date,

        "meeting":
            meeting,

        "track":
            track,

        "races":
            races
    }


def make_output_path(file_path):
    """
    Create output JSON filename.
    """

    return (
        OUTPUT_FOLDER /
        f"{file_path.stem}.json"
    )


def process_all_results():

    OUTPUT_FOLDER.mkdir(
        parents=True,
        exist_ok=True
    )

    files = sorted(
        INPUT_FOLDER.glob("*.txt")
    )

    print("\n" + "=" * 60)
    print("PARSING RESULT DATA")
    print("=" * 60)

    print(
        f"Result files found: "
        f"{len(files)}"
    )

    success_count = 0
    failed_count = 0

    for file_path in files:

        try:

            parsed_data = (
                parse_result_file(
                    file_path
                )
            )

            output_path = (
                make_output_path(
                    file_path
                )
            )

            output_path.write_text(
                json.dumps(
                    parsed_data,
                    indent=4,
                    ensure_ascii=False
                ),
                encoding="utf-8"
            )

            print(
                f"Parsed: "
                f"{file_path.name}"
            )

            print(
                f"Races found: "
                f"{len(parsed_data['races'])}"
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
    print("RESULT PARSING COMPLETE")
    print("=" * 60)

    print(
        f"Successful: "
        f"{success_count}"
    )

    print(
        f"Failed: "
        f"{failed_count}"
    )


if __name__ == "__main__":
    process_all_results()
