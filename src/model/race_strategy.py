"""Discipline-aware data checklist for each race.

This module selects the checks appropriate to the race type and reports source
coverage. It intentionally does not alter model probabilities, selections, or
the economic betting gate.
"""
from __future__ import annotations

from typing import Any, Sequence

from src.model.race_type import canonical_race_type, race_type_family


STRATEGIES = {
    "flat": {
        "label": "flat",
        "required_inputs": ("performance", "weight", "draw", "jockey", "trainer", "going", "surface"),
        "checks": [
            "Parse recent flat form tokens with flat-racing semantics.",
            "Compare carried weight and draw in the context of field size and course layout.",
            "Check going and surface suitability; report them missing when not supplied.",
            "Use only prior trainer/jockey and course/distance records.",
        ],
    },
    "trot_harness": {
        "label": "trotting — harness",
        "required_inputs": ("performance", "listed_chrono", "gains", "driver", "trainer", "start_method"),
        "checks": [
            "Decode trotting form markers (including disqualifications and non-finishes) using trotting rules.",
            "Compare listed kilometre record and distance; do not treat the chrono as a flat-racing time.",
            "Check start method and any handicap/start-position conditions where supplied.",
            "Use only prior driver/trainer, course, distance and recency statistics.",
        ],
    },
    "trot_mounted": {
        "label": "trotting — mounted",
        "required_inputs": ("performance", "listed_chrono", "gains", "jockey", "trainer", "start_method"),
        "checks": [
            "Decode mounted-trot form independently from harness results.",
            "Compare listed kilometre record and distance under mounted-trot conditions.",
            "Prioritize rider/horse experience and prior trainer results; do not silently substitute harness-only form.",
            "Check start method or handicap conditions where supplied.",
        ],
    },
    "obstacle": {
        "label": "obstacle",
        "required_inputs": ("performance", "jockey", "trainer", "going", "surface"),
        "checks": [
            "Prioritize verified obstacle starts and completion/non-finish history.",
            "Separate hurdle and steeplechase history where data supports it.",
            "Check going, course and distance suitability.",
            "Use only prior jockey/trainer statistics and verified results.",
        ],
    },
    "unknown": {
        "label": "unclassified discipline",
        "required_inputs": ("performance",),
        "checks": [
            "Do not apply a discipline-specific scoring rule until the type is identified.",
            "Use only validated generic history and race metadata; flag the classification gap.",
            "Keep the shared model as the fallback and surface the missing evidence.",
        ],
    },
}


def _present(value: Any) -> bool:
    return value not in (None, "")


def _has_history(row: dict[str, Any], field: str) -> bool:
    try:
        return float(row.get(field) or 0) > 0
    except (TypeError, ValueError):
        return False


def build_race_strategy(race_type: Any, rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Return the selected analysis checklist plus measurable input coverage."""
    canonical = canonical_race_type(race_type)
    family = race_type_family(canonical)
    spec = STRATEGIES[family]
    runner_rows = [row for row in rows if isinstance(row, dict)]
    n = len(runner_rows)

    coverage = {}
    for field in spec["required_inputs"]:
        present = sum(_present(row.get(field)) for row in runner_rows)
        coverage[field] = {
            "present_runners": int(present),
            "total_runners": n,
            "coverage": round(present / n, 4) if n else 0.0,
        }

    gaps = [
        {"field": field, "coverage": details["coverage"]}
        for field, details in coverage.items()
        if n == 0 or details["coverage"] < 0.80
    ]
    history = {
        field: round(sum(_has_history(row, field) for row in runner_rows) / n, 4) if n else 0.0
        for field in ("history_starts", "course_starts", "distance_starts")
    }
    raw_average = sum(item["coverage"] for item in coverage.values()) / len(coverage) if coverage else 0.0
    evidence_status = "adequate_inputs" if raw_average >= 0.80 and not gaps else (
        "partial_inputs" if raw_average >= 0.50 else "weak_inputs"
    )

    return {
        "schema_version": 1,
        "canonical_race_type": canonical or "UNKNOWN",
        "family": family,
        "discipline_label": spec["label"],
        "runner_count": n,
        "checks": list(spec["checks"]),
        "required_input_coverage": coverage,
        "critical_data_gaps": gaps,
        "prior_history_coverage": history,
        "evidence_status": evidence_status,
        "model_policy": {
            "current_model": "shared_v3_model",
            "discipline_specific_model": False,
            "discipline_specific_model_status": "not_yet_validated",
            "checklist_changes_ranking": False,
            "checklist_overrides_betting_guard": False,
            "unknown_type_uses_specialist_rules": False,
        },
    }
