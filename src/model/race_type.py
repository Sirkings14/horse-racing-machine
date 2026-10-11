"""Canonical race discipline labels shared by ingestion and modelling.

Unknown labels are preserved in normalized form for auditability. These helpers
classify a race; they do not make a prediction or relax any betting guard.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any


def _token(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.upper().replace("’", "'").replace("'", " ")
    return re.sub(r"[^A-Z0-9]+", " ", text).strip()


_ALIASES = {
    # Flat / galop
    "PLAT": "PLAT",
    "FLAT": "PLAT",
    "FLAT RACE": "PLAT",
    "FLAT RACING": "PLAT",
    "GALOP PLAT": "PLAT",
    # Harness trotting
    "ATTELE": "ATTELE",
    "TROT ATTELE": "ATTELE",
    "TROTTING ATTELE": "ATTELE",
    "HARNESS": "ATTELE",
    "HARNESS TROT": "ATTELE",
    "TROT HARNESS": "ATTELE",
    # Mounted trotting
    "MONTE": "MONTE",
    "TROT MONTE": "MONTE",
    "TROTTING MONTE": "MONTE",
    "MOUNTED TROT": "MONTE",
    "TROT MOUNTED": "MONTE",
    # Hurdles and steeplechase
    "HAIE": "HAIES",
    "HAIES": "HAIES",
    "HURDLE": "HAIES",
    "HURDLES": "HAIES",
    "HURDLE RACE": "HAIES",
    "STEEPLECHASE": "STEEPLE-CHASE",
    "STEEPLE CHASE": "STEEPLE-CHASE",
    "STEEPLE CHASES": "STEEPLE-CHASE",
    "OBSTACLE": "OBSTACLE",
    "OBSTACLES": "OBSTACLE",
    "JUMP": "OBSTACLE",
    "JUMPS": "OBSTACLE",
    "JUMP RACING": "OBSTACLE",
    "CROSS COUNTRY": "OBSTACLE",
    "CROSS COUNTRY OBSTACLE": "OBSTACLE",
}


def canonical_race_type(value: Any) -> str | None:
    """Return a stable internal label while preserving normalized unknowns."""
    token = _token(value)
    if not token:
        return None
    return _ALIASES.get(token, token)


def race_type_family(value: Any) -> str:
    """Return the modelling family without collapsing harness and mounted trot."""
    race_type = canonical_race_type(value)
    if race_type == "PLAT":
        return "flat"
    if race_type == "ATTELE":
        return "trot_harness"
    if race_type == "MONTE":
        return "trot_mounted"
    if race_type in {"HAIES", "STEEPLE-CHASE", "OBSTACLE"}:
        return "obstacle"
    return "unknown"


def race_type_feature_groups(value: Any) -> tuple[float, float, float]:
    """Return backward-compatible (flat, trot, obstacle) indicators for V3."""
    family = race_type_family(value)
    return (
        1.0 if family == "flat" else 0.0,
        1.0 if family in {"trot_harness", "trot_mounted"} else 0.0,
        1.0 if family == "obstacle" else 0.0,
    )
