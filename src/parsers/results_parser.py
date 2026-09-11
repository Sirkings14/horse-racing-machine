from pathlib import Path
from datetime import datetime
import json
import re
from typing import List, Dict, Any, Optional


INPUT_FOLDER = Path("data/processed/results")
OUTPUT_FOLDER = Path("data/structured/results")


def extract_date(text: str) -> Optional[str]:
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
        re.IGNORECASE,
    )

    if not match:
        return None

    day = match.group(1)
    month = match.group(2)
    year = match.group(3)

    return f"{year}-{month}-{day}"


def extract_meeting(text: str) -> Optional[int]:
    """
    Extract meeting number.

    Example:
    REUNION - 5
    """

    match = re.search(
        r"REUNION\s*-?\s*(\d+)",
        text,
        re.IGNORECASE,
    )

    if not match:
        return None

    return int(match.group(1))


def extract_track(text: str) -> Optional[str]:
    """
    Extract track name.

    Example:
    ( VIRE )
    """

    match = re.search(
        r"\(\s*([A-ZÀ-Ÿ'\-\s]+?)\s*\)",
        text,
    )

    if not match:
        return None

    track = " ".join(
        match.group(1).strip().split()
    )

    return track


def clean_number_sequence(
    values: List[str],
) -> List[int]:
    """
    Convert extracted numeric tokens to integers
    and remove duplicates while preserving order.
    """

    output: List[int] = []
    seen = set()

    for value in values:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue

        if number <= 0:
            continue

        if number in seen:
            continue

        seen.add(number)
        output.append(number)

    return output


def extract_arrival_from_line(
    line: str,
) -> Optional[Dict[str, Any]]:
    """
    Extract one race arrival from a single line.

    Supported examples:

        1ère 3 - 9 - 8
        2ième 6 - 10 - 11
        3ème 5 - 2 - 14 - 7 - 9

    The parser captures every horse number that appears
    in the arrival portion of the line.

    It does NOT invent missing positions.
    """

    pattern = re.compile(
        r"^\s*"
        r"(?P<race>\d+)"
        r"\s*"
        r"(?:"
        r"ère|"
        r"er|"
        r"ieme|"
        r"ième|"
        r"ème|"
        r"eme|"
        r"e"
        r")"
        r"\s*"
        r"(?P<arrival>.+?)"
        r"\s*$",
        re.IGNORECASE,
    )

    match = pattern.match(line)

    if not match:
        return None

    race_number = int(
        match.group("race")
    )

    arrival_text = match.group("arrival")

    # Keep only a sequence of horse numbers separated
    # by common separators. This avoids accidentally
    # consuming prize amounts or unrelated numeric data.
    number_tokens = re.findall(
        r"\d+",
        arrival_text,
    )

    arrival = clean_number_sequence(
        number_tokens
    )

    if not arrival:
        return None

    return {
        "race_number": race_number,
        "arrival": arrival,
    }


def extract_arrival_from_text_fallback(
    text: str,
) -> List[Dict[str, Any]]:
    """
    Fallback parser for documents where arrival information
    is not cleanly separated line-by-line.

    Example:

        1ère 3 - 9 - 8
        2ième 6 - 10 - 11

    This uses the same race-label structure but searches
    globally through the text.
    """

    pattern = re.compile(
        r"(?P<race>\d+)"
        r"\s*"
        r"(?:"
        r"ère|"
        r"er|"
        r"ieme|"
        r"ième|"
        r"ème|"
        r"eme|"
        r"e"
        r")"
        r"\s+"
        r"(?P<arrival>"
        r"\d+(?:\s*[-;/]\s*\d+)+"
        r")",
        re.IGNORECASE,
    )

    races: List[Dict[str, Any]] = []

    for match in pattern.finditer(text):
        race_number = int(
            match.group("race")
        )

        arrival_text = match.group("arrival")

        number_tokens = re.findall(
            r"\d+",
            arrival_text,
        )

        arrival = clean_number_sequence(
            number_tokens
        )

        if not arrival:
            continue

        races.append(
            {
                "race_number": race_number,
                "arrival": arrival,
            }
        )

    return races


def extract_race_arrivals(
    text: str,
) -> List[Dict[str, Any]]:
    """
    Extract race arrivals.

    First attempts line-by-line extraction.

    If that produces nothing, falls back to a global
    text search.

    The parser preserves every arrival position that is
    actually available in the processed text.
    """

    races_by_number: Dict[int, Dict[str, Any]] = {}

    lines = text.splitlines()

    for line in lines:
        result = extract_arrival_from_line(
            line
        )

        if result is None:
            continue

        race_number = result["race_number"]

        races_by_number[race_number] = result

    if not races_by_number:
        fallback_races = (
            extract_arrival_from_text_fallback(
                text
            )
        )

        for race in fallback_races:
            race_number = race["race_number"]

            if race_number not in races_by_number:
                races_by_number[race_number] = race

    races: List[Dict[str, Any]] = []

    for race_number in sorted(
        races_by_number.keys()
    ):
        race = races_by_number[race_number]

        arrival = race["arrival"]

        output = {
            "race_number": race_number,
            "arrival": arrival,
            "winner": arrival[0] if len(arrival) >= 1 else None,
            "second": arrival[1] if len(arrival) >= 2 else None,
            "third": arrival[2] if len(arrival) >= 3 else None,
        }

        if len(arrival) >= 4:
            output["fourth"] = arrival[3]

        if len(arrival) >= 5:
            output["fifth"] = arrival[4]

        races.append(output)

    return races


def parse_result_file(
    file_path: Path,
) -> Dict[str, Any]:
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
            races,
    }


def make_output_path(
    file_path: Path,
) -> Path:
    """
    Create output JSON filename.
    """

    return (
        OUTPUT_FOLDER
        / f"{file_path.stem}.json"
    )


def process_all_results() -> None:

    OUTPUT_FOLDER.mkdir(
        parents=True,
        exist_ok=True,
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

    total_races = 0
    total_arrival_positions = 0

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
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            race_count = len(
                parsed_data["races"]
            )

            arrival_positions = sum(
                len(race["arrival"])
                for race in parsed_data["races"]
            )

            total_races += race_count
            total_arrival_positions += (
                arrival_positions
            )

            print(
                f"Parsed: "
                f"{file_path.name}"
            )

            print(
                f"Races found: "
                f"{race_count}"
            )

            print(
                f"Arrival positions captured: "
                f"{arrival_positions}"
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

    print(
        f"Total races extracted: "
        f"{total_races}"
    )

    print(
        f"Total arrival positions captured: "
        f"{total_arrival_positions}"
    )


if __name__ == "__main__":
    process_all_results()
