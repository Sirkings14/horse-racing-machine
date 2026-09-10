import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path


def normalize_text(value):
    """
    Normalize text for reliable comparisons.
    """

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


def normalize_track(track):
    """
    Normalize race track names.
    """

    track = normalize_text(track)

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


def normalize_date(value):
    """
    Normalize date to YYYY-MM-DD.
    """

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

            return datetime.strptime(
                value,
                date_format,
            ).strftime(
                "%Y-%m-%d"
            )

        except ValueError:

            pass

    return None


def get_race_number(race):
    """
    Extract race number safely.
    """

    if not isinstance(
        race,
        dict,
    ):
        return None

    possible_locations = [

        race,

        race.get(
            "race",
            {},
        ),

    ]

    for location in possible_locations:

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
                key,
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


def get_race_date(race):
    """
    Get date from either
    top-level or nested race object.
    """

    if not isinstance(
        race,
        dict,
    ):
        return None

    date = race.get(
        "date"
    )

    if date:

        return normalize_date(
            date
        )

    nested_race = race.get(
        "race",
        {}
    )

    if isinstance(
        nested_race,
        dict,
    ):

        return normalize_date(
            nested_race.get(
                "date"
            )
        )

    return None


def get_race_track(race):
    """
    Get track from either
    top-level or nested race object.
    """

    if not isinstance(
        race,
        dict,
    ):
        return ""

    track = race.get(
        "track"
    )

    if track:

        return normalize_track(
            track
        )

    nested_race = race.get(
        "race",
        {}
    )

    if isinstance(
        nested_race,
        dict,
    ):

        return normalize_track(
            nested_race.get(
                "track"
            )
        )

    return ""


def get_horse_names(race):
    """
    Extract normalized horse names.
    """

    horses = race.get(
        "horses",
        [],
    )

    if not horses:

        nested_race = race.get(
            "race",
            {},
        )

        if isinstance(
            nested_race,
            dict,
        ):

            horses = nested_race.get(
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


def calculate_match(
    program_race,
    result_race,
):
    """
    Calculate confidence score.
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

    # DATE

    if program_date and result_date:

        max_score += 40

        if program_date == result_date:

            score += 40

            reasons.append(
                "date exact"
            )

    # TRACK

    if program_track and result_track:

        max_score += 30

        if program_track == result_track:

            score += 30

            reasons.append(
                "track exact"
            )

    # RACE NUMBER

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

    # HORSE OVERLAP

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

        overlap = (

            len(
                program_horses
                & result_horses
            )

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


def load_json_files(folder):
    """
    Load all JSON files.
    """

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


def create_race_key(race):
    """
    Create stable race identity key.
    """

    date = get_race_date(
        race
    )

    track = get_race_track(
        race
    )

    number = get_race_number(
        race
    )

    return (

        date,

        track,

        number,

    )


def deduplicate_races(races):
    """
    Remove duplicate races.

    A race must have at least:
    date + race number.

    Track is used when available.
    """

    unique = {}

    result = []

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

        # Cannot safely deduplicate
        # without date and race number.

        if (

            not date

            or number is None

        ):

            result.append(
                race
            )

            continue

        # Primary key

        key = (

            date,

            track,

            number,

        )

        # If track is missing,
        # still prevent exact duplicates
        # from appearing repeatedly.

        if key not in unique:

            unique[key] = race

            result.append(
                race
            )

    return result


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


def match_races(
    programs,
    results,
    threshold=75,
):
    """
    Match program races
    against result races.
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

            if best_index is not None:

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
    """
    Run race matching engine.
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


if __name__ == "__main__":

    run_matching()
