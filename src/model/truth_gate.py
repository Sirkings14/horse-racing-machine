from __future__ import annotations

import re
from typing import Any

RESULT_MARKERS = (
    "RESULTATS DES COURSES",
    "RÉSULTATS DES COURSES",
    "ARRIVEE DU",
    "ARRIVÉE DU",
    "ARRIVEE:",
    "ARRIVÉE:",
    "RAPPORTS",
)

TAIL_MARKERS = (
    "JOURNAL HIPPIQUE",
    "LES MEILLEURS DE LA SEMAINE",
    "PMU’B...",
    "PMU'B...",
)

PRESS_FIELDS = ("favorites_rank", "form_rank", "class_rank", "progress_rank", "regularity_rank")


def _first_marker_position(text: str, markers: tuple[str, ...]) -> int | None:
    upper = text.upper()
    positions = [upper.find(marker.upper()) for marker in markers]
    positions = [p for p in positions if p >= 0]
    return min(positions) if positions else None


def prerace_only(text: str) -> str:
    """Return only information available before the race.

    Result/report sections are hard cut. This is deliberately conservative:
    false removal is preferable to contaminating training with post-race truth.
    """
    if not text:
        return ""
    positions = []
    for markers in (RESULT_MARKERS, TAIL_MARKERS):
        position = _first_marker_position(text, markers)
        if position is not None:
            positions.append(position)
    cut = min(positions) if positions else len(text)
    cleaned = text[:cut]
    cleaned = re.sub(r"\b(?:ARRIVEE|ARRIVÉE)\s*[:\-].*$", "", cleaned, flags=re.I | re.M)
    return re.sub(r"\s+", " ", cleaned).strip()


def strip_press_rankings(row: dict[str, Any]) -> dict[str, Any]:
    """Remove press-derived ranking inputs from a feature row."""
    return {k: v for k, v in row.items() if k not in PRESS_FIELDS}


def validate_program(program: dict[str, Any]) -> dict[str, Any]:
    race = program.get("race") or {}
    horses = program.get("horses") or []
    expected = race.get("runners_count")
    numbers = []
    for horse in horses:
        try:
            numbers.append(int(horse.get("number")))
        except (TypeError, ValueError):
            pass

    errors: list[str] = []
    warnings: list[str] = []
    if not program.get("date"):
        errors.append("missing_race_date")
    if not race.get("track"):
        errors.append("missing_track")
    if not race.get("race_number"):
        errors.append("missing_race_number")
    if expected is None:
        errors.append("missing_runner_count")
    elif len(horses) != int(expected):
        errors.append("runner_count_mismatch")
    if len(numbers) != len(set(numbers)):
        errors.append("duplicate_horse_numbers")
    if expected is not None and any(n < 1 or n > int(expected) for n in numbers):
        errors.append("horse_number_out_of_range")

    distance = race.get("distance")
    try:
        distance_value = int(distance)
    except (TypeError, ValueError):
        distance_value = 0
    if distance_value and not 800 <= distance_value <= 7000:
        errors.append("implausible_distance")

    if "published_arrival" in program and program.get("published_arrival"):
        warnings.append("published_arrival_present_but_excluded_from_features")

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "press_independent": True,
        "post_race_data_excluded": True,
    }
