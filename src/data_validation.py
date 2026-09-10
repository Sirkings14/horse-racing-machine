import re
import unicodedata
from datetime import datetime


# ============================================================
# TEXT NORMALIZATION
# ============================================================


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


# ============================================================
# TRACK NORMALIZATION
# ============================================================


def normalize_track(track):
    """
    Normalize race track names.
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


# ============================================================
# DATE NORMALIZATION
# ============================================================


def normalize_date(value):
    """
    Normalize date to YYYY-MM-DD.
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

            continue

    return None


# ============================================================
# SAFE RACE FIELD EXTRACTION
# ============================================================


def get_race_date(record):
    """
    Extract race date from multiple
    possible parser structures.
    """

    if not isinstance(
        record,
        dict,
    ):
        return None

    # Top-level

    value = record.get(
        "date"
    )

    if value:

        return normalize_date(
            value
        )

    # Nested race object

    race = record.get(
        "race",
        {}
    )

    if isinstance(
        race,
        dict,
    ):

        value = race.get(
            "date"
        )

        if value:

            return normalize_date(
                value
            )

    return None


def get_race_track(record):
    """
    Extract race track from multiple
    possible parser structures.
    """

    if not isinstance(
        record,
        dict,
    ):
        return ""

    value = record.get(
        "track"
    )

    if value:

        return normalize_track(
            value
        )

    race = record.get(
        "race",
        {}
    )

    if isinstance(
        race,
        dict,
    ):

        value = race.get(
            "track"
        )

        if value:

            return normalize_track(
                value
            )

    return ""


def get_race_number(record):
    """
    Extract race number safely.
    """

    if not isinstance(
        record,
        dict,
    ):
        return None

    locations = [

        record,

        record.get(
            "race",
            {},
        ),

    ]

    for location in locations:

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
                str(
                    value
                ),
            )

            if match:

                return int(
                    match.group()
                )

    return None


def get_horses(record):
    """
    Extract horses from multiple
    possible parser structures.
    """

    if not isinstance(
        record,
        dict,
    ):
        return []

    horses = record.get(
        "horses"
    )

    if not horses:

        race = record.get(
            "race",
            {}
        )

        if isinstance(
            race,
            dict,
        ):

            horses = race.get(
                "horses",
                []
            )

    if not isinstance(
        horses,
        list,
    ):

        return []

    return horses


# ============================================================
# HORSE NORMALIZATION
# ============================================================


def normalize_horse(
    horse,
):
    """
    Convert any horse representation
    into canonical structure.
    """

    if isinstance(
        horse,
        str,
    ):

        name = normalize_text(
            horse
        )

        if not name:

            return None

        return {

            "number": None,

            "name": name,

            "position": None,

        }

    if not isinstance(
        horse,
        dict,
    ):

        return None

    name = (

        horse.get("name")

        or horse.get("horse")

        or horse.get("horse_name")

    )

    if not name:

        return None

    number = (

        horse.get("number")

        or horse.get("horse_number")

        or horse.get("num")

    )

    position = (

        horse.get("position")

        or horse.get("rank")

        or horse.get("place")

        or horse.get("arrival_position")

    )

    return {

        "number":
            number,

        "name":
            normalize_text(
                name
            ),

        "position":
            position,

    }


# ============================================================
# CANONICALIZATION
# ============================================================


def canonicalize_race(
    record,
    source_type=None,
    source_file=None,
):
    """
    Convert any parser output into
    one canonical race structure.
    """

    if not isinstance(
        record,
        dict,
    ):

        return None

    horses = []

    for horse in get_horses(
        record
    ):

        normalized = normalize_horse(
            horse
        )

        if normalized:

            horses.append(
                normalized
            )

    canonical = {

        "source_type":
            source_type
            or record.get(
                "source_type"
            ),

        "source_file":
            source_file
            or record.get(
                "source_file"
            ),

        "race": {

            "date":
                get_race_date(
                    record
                ),

            "track":
                get_race_track(
                    record
                ),

            "race_number":
                get_race_number(
                    record
                ),

        },

        "horses":
            horses,

    }

    return canonical


# ============================================================
# VALIDATION
# ============================================================


def validate_race(
    race,
    require_track=True,
    require_horses=True,
):
    """
    Validate canonical race.
    """

    errors = []

    if not isinstance(
        race,
        dict,
    ):

        return {

            "valid":
                False,

            "errors":
                [
                    "INVALID_RACE_OBJECT"
                ],

        }

    race_info = race.get(
        "race",
        {}
    )

    if not isinstance(
        race_info,
        dict,
    ):

        errors.append(
            "MISSING_RACE_OBJECT"
        )

        race_info = {}

    date = race_info.get(
        "date"
    )

    track = race_info.get(
        "track"
    )

    number = race_info.get(
        "race_number"
    )

    horses = race.get(
        "horses",
        []
    )

    if not date:

        errors.append(
            "MISSING_DATE"
        )

    if require_track and not track:

        errors.append(
            "MISSING_TRACK"
        )

    if number is None:

        errors.append(
            "MISSING_RACE_NUMBER"
        )

    if require_horses and not horses:

        errors.append(
            "MISSING_HORSES"
        )

    return {

        "valid":
            len(errors) == 0,

        "errors":
            errors,

    }


# ============================================================
# RACE EXTRACTION
# ============================================================


def extract_races(
    data,
):
    """
    Extract individual races from
    known JSON structures.

    This is the safety boundary
    between parsers and the
    rest of the machine.
    """

    # Direct list

    if isinstance(
        data,
        list,
    ):

        return data

    if not isinstance(
        data,
        dict,
    ):

        return []

    # Container with races

    if isinstance(
        data.get(
            "races"
        ),
        list,
    ):

        return data[
            "races"
        ]

    # Single race object

    if (

        get_race_date(
            data
        )

        or

        get_race_number(
            data
        )

        or

        get_race_track(
            data
        )

    ):

        return [
            data
        ]

    return []


# ============================================================
# DATASET HEALTH CHECK
# ============================================================


def dataset_health(
    races,
):
    """
    Calculate dataset health.
    """

    total = len(
        races
    )

    valid = 0

    invalid = 0

    error_counts = {}

    for race in races:

        validation = validate_race(
            race
        )

        if validation[
            "valid"
        ]:

            valid += 1

        else:

            invalid += 1

            for error in validation[
                "errors"
            ]:

                error_counts[
                    error
                ] = (

                    error_counts.get(
                        error,
                        0,
                    )

                    + 1

                )

    return {

        "total":
            total,

        "valid":
            valid,

        "invalid":
            invalid,

        "errors":
            error_counts,

    }
