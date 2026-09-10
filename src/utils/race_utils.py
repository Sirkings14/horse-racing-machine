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
    Normalize race track names so different
    representations of the same track match.
    """

    track = normalize_text(
        track
    )

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
    Normalize supported date formats
    to YYYY-MM-DD.
    """

    if not value:
        return None

    value = str(
        value
    ).strip()

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

    Supports both:

    {
        "race_number": 4
    }

    and:

    {
        "race": {
            "race_number": 4
        }
    }
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
                key
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
    Get race date from either:

    - race itself
    - nested race object
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

        date = nested_race.get(
            "date"
        )

        if date:

            return normalize_date(
                date
            )

    return None


def get_race_track(race):
    """
    Get normalized track from either:

    - race itself
    - nested race object
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

        track = nested_race.get(
            "track"
        )

        if track:

            return normalize_track(
                track
            )

    return ""


def get_horse_names(race):
    """
    Extract normalized horse names.

    Result data may not contain horse names.
    In that case this correctly returns
    an empty set.
    """

    if not isinstance(
        race,
        dict,
    ):
        return set()

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

    if not isinstance(
        horses,
        list,
    ):

        return names

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

                normalized = normalize_text(
                    name
                )

                if normalized:

                    names.add(
                        normalized
                    )

        elif isinstance(
            horse,
            str,
        ):

            normalized = normalize_text(
                horse
            )

            if normalized:

                names.add(
                    normalized
                )

    return names


def expand_record(record):
    """
    Convert a document into individual races.

    This is especially important for
    result parser output.

    Example input:

    {
        "document_type": "result",
        "date": "2026-09-06",
        "track": "VIRE",
        "meeting": 5,
        "races": [
            {
                "race_number": 1,
                "arrival": [3, 9, 8]
            },
            {
                "race_number": 2,
                "arrival": [6, 10, 11]
            }
        ]
    }

    Output:

    [
        {
            "date": "2026-09-06",
            "track": "VIRE",
            "meeting": 5,
            "race_number": 1,
            "arrival": [3, 9, 8]
        },
        {
            "date": "2026-09-06",
            "track": "VIRE",
            "meeting": 5,
            "race_number": 2,
            "arrival": [6, 10, 11]
        }
    ]
    """

    if not isinstance(
        record,
        dict,
    ):
        return []

    races = record.get(
        "races"
    )

    # --------------------------------------------------------
    # DOCUMENT CONTAINS MULTIPLE RACES
    # --------------------------------------------------------

    if isinstance(
        races,
        list,
    ):

        expanded = []

        parent_date = record.get(
            "date"
        )

        parent_track = record.get(
            "track"
        )

        parent_meeting = record.get(
            "meeting"
        )

        for race in races:

            if not isinstance(
                race,
                dict,
            ):

                continue

            expanded_race = dict(
                race
            )

            # Inherit date from document.

            if not expanded_race.get(
                "date"
            ):

                expanded_race[
                    "date"
                ] = parent_date

            # Inherit track from document.

            if not expanded_race.get(
                "track"
            ):

                expanded_race[
                    "track"
                ] = parent_track

            # Inherit meeting.

            if (
                not expanded_race.get(
                    "meeting"
                )
                and parent_meeting
                is not None
            ):

                expanded_race[
                    "meeting"
                ] = parent_meeting

            expanded.append(
                expanded_race
            )

        return expanded

    # --------------------------------------------------------
    # ALREADY AN INDIVIDUAL RACE
    # --------------------------------------------------------

    return [
        record
    ]


def expand_records(records):
    """
    Expand a list of program/result documents
    into a flat list of individual races.
    """

    expanded = []

    if not isinstance(
        records,
        list,
    ):

        return expanded

    for record in records:

        expanded.extend(
            expand_record(
                record
            )
        )

    return expanded
