from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.matching.race_matcher import normalize_track

BASE_DIR = Path(__file__).resolve().parents[2]
PROGRAMS_DIR = BASE_DIR / "data" / "structured" / "programs"
HISTORICAL_ROSTERS_FILE = BASE_DIR / "data" / "rosters" / "historical_rosters.json"


def canonical_key(date: Any, track: Any, race_number: Any) -> str | None:
    try:
        number = int(race_number)
    except (TypeError, ValueError):
        return None
    date_text = str(date or "")[:10]
    track_text = normalize_track(track)
    if not date_text or not track_text:
        return None
    return f"{date_text}|{track_text}|{number}"


def build_program_runner_index() -> dict[str, dict[str, Any]]:
    """Build an authoritative roster index, failing closed on conflicting copies.

    The repository can contain multiple parses/copies of the same program. Never
    let filesystem iteration order decide which runner list becomes truth.
    Identical rosters are collapsed; conflicting rosters are explicitly marked
    unusable for result verification.
    """
    candidates: dict[str, list[dict[str, Any]]] = {}
        for path in sorted(PROGRAMS_DIR.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict) or payload.get("document_type") != "program":
            continue

        race = payload.get("race") or {}
        key = canonical_key(
            payload.get("date") or race.get("date"),
            race.get("track") or payload.get("track"),
            race.get("race_number") if race.get("race_number") is not None else payload.get("race_number"),
        )
        if not key:
            continue

        horse_numbers = set()
        for horse in payload.get("horses") or []:
            try:
                number = int(horse.get("number"))
            except (TypeError, ValueError):
                continue
            if number > 0:
                horse_numbers.add(number)

        if horse_numbers:
            candidates.setdefault(key, []).append({
                "horse_numbers": horse_numbers,
                "runners_count": len(horse_numbers),
                "source_file": path.name,
                "source_type": "structured_program",
            })

    historical_conflicts: dict[str, list[str]] = {}
    try:
        historical_payload = json.loads(HISTORICAL_ROSTERS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        historical_payload = {}
    historical_races = historical_payload.get("races", {}) if isinstance(historical_payload, dict) else {}
    if isinstance(historical_races, dict):
        for raw_key, record in historical_races.items():
            parts = str(raw_key).split("|")
            if len(parts) != 3 or not isinstance(record, dict):
                continue
            key = canonical_key(parts[0], parts[1], parts[2])
            if not key:
                continue
            if record.get("conflict"):
                historical_conflicts[key] = [
                    "historical_rosters.json:" + str(value)
                    for value in (record.get("conflicting_source_meta_keys") or [])
                ] or ["historical_rosters.json:conflicting_complete_rosters"]
                continue
            try:
                expected = int(record.get("runners_count") or 0)
                numbers = {int(value) for value in record.get("horse_numbers") or [] if int(value) > 0}
            except (TypeError, ValueError):
                continue
            if expected <= 0 or len(numbers) != expected:
                continue
            candidates.setdefault(key, []).append({
                "horse_numbers": numbers,
                "runners_count": expected,
                "source_file": "historical_rosters.json",
                "source_type": "historical_participant_roster",
            })

    index: dict[str, dict[str, Any]] = {}
    for key in sorted(set(candidates) | set(historical_conflicts)):
        copies = candidates.get(key, [])
        if key in historical_conflicts:
            index[key] = {
                "horse_numbers": set(),
                "runners_count": 0,
                "source_file": None,
                "source_count": len(copies) + 1,
                "conflict": True,
                "conflicting_sources": sorted(
                    [item["source_file"] for item in copies] + historical_conflicts[key]
                ),
            }
            continue
        roster_signatures = {tuple(sorted(item["horse_numbers"])) for item in copies}
        if len(roster_signatures) == 1:
            # Stable source attribution is useful for audits and reproducibility.
            selected = min(copies, key=lambda item: (0 if item.get("source_type") == "structured_program" else 1, item["source_file"]))
            index[key] = {
                **selected,
                "source_count": len(copies),
                "conflict": False,
            }
        else:
            index[key] = {
                "horse_numbers": set(),
                "runners_count": 0,
                "source_file": None,
                "source_count": len(copies),
                "conflict": True,
                "conflicting_sources": sorted(item["source_file"] for item in copies),
            }
    return index

def validate_arrival(
    race_key: str,
    arrival: list[int],
    program_index: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Validate result truth against the race's actual declared horse numbers.

    We reject, rather than silently repair, an arrival containing an unknown horse
    number. This prevents payouts, money amounts, distances, or OCR artifacts from
    becoming training truth.
    """
    meta = program_index.get(race_key)
    if not meta:
        return {
            "accepted_for_learning": False,
            "reason": "program_roster_unavailable",
            "race_key": race_key,
            "arrival_positions_available": len(arrival),
        }

    if meta.get("conflict"):
        return {
            "accepted_for_learning": False,
            "reason": "conflicting_program_rosters",
            "race_key": race_key,
            "arrival_positions_available": len(arrival),
            "conflicting_sources": meta.get("conflicting_sources", []),
        }

    expected = meta["horse_numbers"]
    unknown = [number for number in arrival if number not in expected]
    duplicates = sorted({number for number in arrival if arrival.count(number) > 1})

    reasons: list[str] = []
    if len(arrival) < 3:
        reasons.append("fewer_than_three_arrival_positions")
    if duplicates:
        reasons.append("duplicate_arrival_numbers")
    if unknown:
        reasons.append("arrival_contains_non_runner_numbers")
    if len(arrival) > len(expected):
        reasons.append("arrival_exceeds_declared_field_size")

    accepted = not reasons

    return {
        "accepted_for_learning": accepted,
        "reason": "validated_against_program_roster" if accepted else ";".join(reasons),
        "race_key": race_key,
        "arrival_positions_available": len(arrival),
        "declared_runner_count": len(expected),
        "unknown_numbers": unknown,
        "duplicate_numbers": duplicates,
        "program_source": meta["source_file"],
    }
