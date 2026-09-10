import re
import unicodedata
from datetime import datetime


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
        character
        for character in value
        if unicodedata.category(character) != "Mn"
    )

    value = value.replace("-", " ")
    value = value.replace("_", " ")

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
    Extract race date.
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
        {},
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
    Extract race track.
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
        {},
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

                horse.get("name")

                or horse.get("horse")

                or horse.get("horse_name")

            )

            if name:

                names.add(
                    normalize_text(name)
                )

        elif isinstance(
            horse,
            str,
        ):

            names.add(
                normalize_text(horse)
            )

    return names


def expand_result_document(document):
    """
    Convert one result document containing
    multiple races into individual race records.

    Example input:

    {
        "date": "2026-09-06",
        "track": "VIRE",
        "races": [
            {
                "race_number": 1,
                "arrival": [3, 9, 8]
            }
        ]
    }

    Output:

    [
        {
            "date": "2026-09-06",
            "track": "VIRE",
            "race_number": 1,
            "arrival": [3, 9, 8]
        }
    ]
    """

    if not isinstance(
        document,
        dict,
    ):
        return []

    races = document.get(
        "races",
        [],
    )

    if not isinstance(
        races,
        list,
    ):
        return []

    document_date = normalize_date(
        document.get(
            "date"
        )
    )

    document_track = normalize_track(
        document.get(
            "track"
        )
    )

    expanded = []

    for race in races:

        if not isinstance(
            race,
            dict,
        ):
            continue

        race_record = dict(
            race
        )

        # Inherit document-level date.

        if not race_record.get(
            "date"
        ):

            race_record[
                "date"
            ] = document_date

        # Inherit document-level track.

        if not race_record.get(
            "track"
        ):

            race_record[
                "track"
            ] = document_track

        expanded.append(
            race_record
        )

    return expanded


def expand_records(records):
    """
    Expand program/result documents into
    individual race records when needed.
    """

    expanded = []

    for record in records:

        if not isinstance(
            record,
            dict,
        ):
            continue

        # Result document containing races.

        if isinstance(
            record.get("races"),
            list,
        ):

            races = expand_result_document(
                record
            )

            if races:

                expanded.extend(
                    races
                )

                continue

        # Already an individual race.

        expanded.append(
            record
        )

    return expanded
