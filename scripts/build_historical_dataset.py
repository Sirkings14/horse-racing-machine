from __future__ import annotations

import ast
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from datasets import load_dataset

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from src.model.historical_profile import build_walk_forward_profiles

OUT = BASE / "data" / "dataset" / "training_dataset_clean.json"
AUDIT_OUT = BASE / "data" / "dataset" / "training_dataset_audit.json"
SOURCE = "annaelmoussa/horse-racing-france"
COHORT_SCHEMA_VERSION = 2


def _pick(d: dict[str, Any], names: list[str], default=None):
    lower = {str(k).lower(): k for k in d}
    for name in names:
        key = lower.get(name.lower())
        if key is not None and d.get(key) not in (None, ""):
            return d[key]
    return default


def _num(value):
    try:
        result = float(str(value).replace(",", "."))
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _integer(value) -> int | None:
    result = _num(value)
    if result is None or result <= 0 or not result.is_integer():
        return None
    return int(result)


def _key(value):
    return str(value or "").strip()


def _participant_key(participant: dict[str, Any]) -> str:
    direct = _key(_pick(participant, ["raceKey", "race_key"]))
    if direct:
        return direct
    course_date = str(_pick(participant, ["date", "date_course"], "") or "")[:10]
    reunion = _integer(_pick(participant, ["numReunion", "reunion_number"]))
    course = _integer(_pick(participant, ["numCourse", "race_number", "course_number"]))
    if course_date and reunion is not None and course is not None:
        return f"{course_date}_R{reunion}_C{course}"
    return ""


def _is_true(value: Any) -> bool:
    """Interpret the dataset's definitive-arrival flag without truthy-string traps."""
    if value is True:
        return True
    if type(value) is int and value == 1:
        return True
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "vrai"}
    return False


def _arrival_positions(value: Any) -> dict[int, int] | None:
    """Parse official arrival groups, preserving dead heats; reject malformed truth.

    The source stores orders as nested groups such as [[7], [2, 4], [5]].
    Each group shares a finishing position; subsequent positions skip the
    number of horses in the tie (competition-ranking semantics).
    """
    if value is None:
        return None
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            value = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            try:
                value = ast.literal_eval(raw)
            except (ValueError, SyntaxError):
                return None
    if not isinstance(value, (list, tuple)) or not value:
        return None

    positions: dict[int, int] = {}
    offset = 0
    for raw_group in value:
        group = list(raw_group) if isinstance(raw_group, (list, tuple)) else [raw_group]
        if not group:
            return None
        parsed: list[int] = []
        for item in group:
            number = _integer(item)
            if number is None or number in positions or number in parsed:
                return None
            parsed.append(number)
        rank = offset + 1
        for number in parsed:
            positions[number] = rank
        offset += len(parsed)

    # Keep the existing evidence policy: at least three classified horses are
    # required before we use a race as target truth for the Top-3 model.
    return positions if len(positions) >= 3 else None


def _target_fields(horse_number: int, arrival_positions: dict[int, int]) -> dict[str, Any]:
    """Top-N negatives include declared starters absent from definitive arrival."""
    position = arrival_positions.get(horse_number)
    return {
        "finish_position": position,
        "won": int(position == 1),
        "top3": int(position is not None and position <= 3),
        "top5": int(position is not None and position <= 5),
    }


def _eligible_training_races(
    race_meta: dict[str, dict[str, Any]],
    participant_row_counts: dict[str, int],
    participant_numbers: dict[str, set[int]],
    duplicate_number_races: set[str],
) -> tuple[set[str], dict[str, int]]:
    """Require definitive outcomes and a complete, unambiguous declared starter set."""
    eligible: set[str] = set()
    audit = {
        "race_metadata_count": len(race_meta),
        "eligible_finalized_races": 0,
        "non_finalized_races": 0,
        "finalized_races_without_valid_arrival": 0,
        "incomplete_or_duplicate_rosters": 0,
        "arrival_numbers_outside_roster": 0,
    }

    for race_key, meta in race_meta.items():
        if not meta.get("arrival_definitive"):
            audit["non_finalized_races"] += 1
            continue
        positions = meta.get("arrival_positions")
        if not isinstance(positions, dict) or len(positions) < 3:
            audit["finalized_races_without_valid_arrival"] += 1
            continue

        try:
            expected = int(meta.get("runners_count") or 0)
        except (TypeError, ValueError):
            expected = 0
        count = participant_row_counts.get(race_key, 0)
        numbers = participant_numbers.get(race_key, set())
        if (
            expected <= 0
            or count != expected
            or len(numbers) != expected
            or race_key in duplicate_number_races
        ):
            audit["incomplete_or_duplicate_rosters"] += 1
            continue
        if not set(positions).issubset(numbers):
            audit["arrival_numbers_outside_roster"] += 1
            continue

        eligible.add(race_key)

    audit["eligible_finalized_races"] = len(eligible)
    return eligible, audit


def main():
    print("Loading race metadata...")
    courses = load_dataset(SOURCE, "courses", split="train", streaming=True)
    race_meta: dict[str, dict[str, Any]] = {}
    for i, course in enumerate(courses):
        race_key = _key(_pick(course, ["raceKey", "race_key"]))
        if not race_key:
            course_date = str(_pick(course, ["date", "date_course"], "") or "")[:10]
            reunion = _integer(_pick(course, ["numReunion", "reunion_number"]))
            number = _integer(_pick(course, ["numCourse", "race_number", "course_number"]))
            if course_date and reunion is not None and number is not None:
                race_key = f"{course_date}_R{reunion}_C{number}"
        if not race_key:
            continue

        arrival_positions = _arrival_positions(
            _pick(course, ["ordreArrivee", "ordre_arrivee", "finish_order"])
        )
        race_meta[race_key] = {
            "date": str(_pick(course, ["date", "date_course"], "") or "")[:10],
            "track": str(_pick(course, ["hippodrome", "track"], "") or ""),
            "race_number": int(_num(_pick(course, ["numCourse", "race_number"], 0)) or 0),
            "distance": int(_num(_pick(course, ["distance"], 0)) or 0),
            "runners_count": int(_num(_pick(course, ["nombreDeclaresPartants", "runners_count"], 0)) or 0),
            "prize_euros": _num(_pick(course, ["montantPrix", "prize_euros", "allocation_eur"])),
            "race_type": str(_pick(course, ["specialite", "discipline", "race_type"], "") or ""),
            "arrival_definitive": _is_true(_pick(course, ["arriveeDefinitive", "arrival_definitive"])),
            "arrival_positions": arrival_positions,
        }
        if i and i % 25000 == 0:
            print("courses:", i)

    print("Race metadata:", len(race_meta))
    participants = load_dataset(SOURCE, "participants", split="train", streaming=True)
    candidate_rows: list[dict[str, Any]] = []
    columns_seen: set[str] = set()
    matched_meta = valid_participant_numbers = 0
    participant_row_counts: dict[str, int] = defaultdict(int)
    participant_numbers: dict[str, set[int]] = defaultdict(set)
    duplicate_number_races: set[str] = set()

    for i, participant in enumerate(participants):
        columns_seen.update(participant.keys())
        race_key = _participant_key(participant)
        meta = race_meta.get(race_key)
        if not meta or not meta.get("date") or not meta.get("track") or not meta.get("race_number"):
            continue
        matched_meta += 1

        horse_number = _integer(_pick(
            participant, ["numero", "num", "numeroPmu", "numPmu", "horse_number", "program_number"]
        ))
        if horse_number is None:
            continue

        participant_row_counts[race_key] += 1
        if horse_number in participant_numbers[race_key]:
            duplicate_number_races.add(race_key)
        participant_numbers[race_key].add(horse_number)
        valid_participant_numbers += 1

        arrival_positions = meta.get("arrival_positions")
        if not meta.get("arrival_definitive") or not isinstance(arrival_positions, dict):
            continue

        targets = _target_fields(horse_number, arrival_positions)
        horse_name = str(
            _pick(participant, ["cheval", "nomCheval", "horse", "horse_name", "nom"], f"HORSE_{horse_number}")
            or f"HORSE_{horse_number}"
        ).strip()
        horse_id = _pick(
            participant,
            ["horse_id", "horseId", "horse_uid", "horseUid", "idCheval", "id_cheval",
             "identifiantCheval", "identifiant_cheval"],
        )
        candidate_rows.append({
            "race_key": race_key,
            "date": meta["date"],
            "track": meta["track"],
            "race_number": meta["race_number"],
            "distance": meta["distance"],
            "runners_count": meta["runners_count"],
            "prize_euros": meta["prize_euros"],
            "race_type": meta["race_type"],
            "horse_number": horse_number,
            "horse_name": horse_name,
            "horse_id": horse_id,
            **targets,
            "weight": _num(_pick(participant, ["poids", "weight", "carried_weight", "poidsporte"])),
            "draw": _num(_pick(participant, ["corde", "draw", "stall", "numCorde", "placeCorde"])),
            "trainer": _pick(participant, ["entraineur", "trainer", "trainer_name"]),
            "driver": _pick(participant, ["driver", "driver_name", "jockey", "jockey_name"]),
            "jockey": _pick(participant, ["jockey", "jockey_name", "driver", "driver_name"]),
            "owner": _pick(participant, ["proprietaire", "owner", "owner_name"]),
            "sex": _pick(participant, ["sexe", "sex"]),
            "age": _num(_pick(participant, ["age"])),
            "performance": _pick(participant, ["musique", "performance", "recent_form", "form"]),
            "gains": _num(_pick(participant, ["gainsCarriere", "gains_carriere", "career_earnings", "earnings"])),
            "win_odds_decimal": _num(_pick(participant, [
                "cotePMU", "cotePmu", "cote_pmu", "odds", "odds_decimal",
                "coteGagnant", "starting_price", "starting_price_decimal"
            ])),
        })

        if i and i % 100000 == 0:
            print(
                "participants:", i,
                "metadata_matches:", matched_meta,
                "valid_runner_numbers:", valid_participant_numbers,
                "candidate_rows:", len(candidate_rows),
            )

    eligible_races, cohort_audit = _eligible_training_races(
        race_meta, participant_row_counts, participant_numbers, duplicate_number_races
    )
    rows = [row for row in candidate_rows if row["race_key"] in eligible_races]
    if not rows:
        raise RuntimeError("No verified starter rows built after cohort validation")

    rows.sort(key=lambda row: (row["date"], row["race_key"], row["horse_number"]))
    unplaced_starters = sum(row["finish_position"] is None for row in rows)
    rows = build_walk_forward_profiles(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")

    odds_rows = sum(row.get("win_odds_decimal") is not None for row in rows)
    audit = {
        "cohort_schema_version": COHORT_SCHEMA_VERSION,
        "source": SOURCE,
        "target_policy": (
            "all declared starters in a complete roster for a definitive arrival; "
            "unlisted starters receive win/top3/top5 negative targets and null finish_position"
        ),
        "dead_heat_policy": "tied horses share their group's competition rank",
        "post_race_features_included": False,
        **cohort_audit,
        "participants_with_valid_numbers": valid_participant_numbers,
        "candidate_rows_before_complete_roster_filter": len(candidate_rows),
        "training_rows": len(rows),
        "training_races": len({row["race_key"] for row in rows}),
        "placed_starter_rows": len(rows) - unplaced_starters,
        "unplaced_starter_rows": unplaced_starters,
        "explicit_win_odds_rows": odds_rows,
        "explicit_win_odds_rate": round(odds_rows / len(rows), 6),
        "first_date": rows[0]["date"],
        "last_date": rows[-1]["date"],
    }
    AUDIT_OUT.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_OUT.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"participant_columns": sorted(columns_seen), **audit}, indent=2))


if __name__ == "__main__":
    main()
