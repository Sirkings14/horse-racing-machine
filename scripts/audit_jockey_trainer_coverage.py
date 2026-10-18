from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
PROGRAMS_DIR = BASE_DIR / "data" / "structured" / "programs"
MATCHED_FILE = BASE_DIR / "data" / "matched" / "matched_races.json"

JOCKEY_KEYS = ("jockey", "driver", "jockey_name", "driver_name", "jockeyName", "driverName")
TRAINER_KEYS = ("trainer", "entraineur", "trainer_name", "trainerName")


def nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def first_value(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = row.get(key)
        if nonempty(value):
            return value
    return None


def norm_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().upper())


def race_key(date_value: Any, track: Any, race_number: Any) -> str | None:
    date_text = str(date_value or "")[:10]
    track_text = norm_text(track)
    try:
        number = int(race_number)
    except (TypeError, ValueError):
        return None
    if not date_text or not track_text:
        return None
    return f"{date_text}|{track_text}|{number}"


def as_object(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def program_race_and_horses(program: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    race = program.get("race")
    horses = program.get("horses")
    return (
        race if isinstance(race, dict) else {},
        [h for h in horses if isinstance(h, dict)] if isinstance(horses, list) else [],
    )


def _coverage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    jockey = sum(nonempty(first_value(row, JOCKEY_KEYS)) for row in rows)
    trainer = sum(nonempty(first_value(row, TRAINER_KEYS)) for row in rows)
    both = sum(
        nonempty(first_value(row, JOCKEY_KEYS)) and nonempty(first_value(row, TRAINER_KEYS))
        for row in rows
    )
    pct = lambda n: round(n / total, 4) if total else 0.0
    return {
        "runners": total,
        "jockey_or_driver_present": jockey,
        "jockey_or_driver_rate": pct(jockey),
        "trainer_present": trainer,
        "trainer_rate": pct(trainer),
        "both_present": both,
        "both_rate": pct(both),
    }


def audit(programs_dir: Path = PROGRAMS_DIR, matched_file: Path = MATCHED_FILE) -> dict[str, Any]:
    """Audit source coverage and verified result linkage only; never changes model inputs."""
    program_rows: list[dict[str, Any]] = []
    program_races: set[str] = set()
    malformed_program_files = 0
    program_files = sorted(programs_dir.glob("*.json")) if programs_dir.exists() else []

    for path in program_files:
        program = as_object(path)
        if program is None:
            malformed_program_files += 1
            continue
        race, horses = program_race_and_horses(program)
        key = race_key(program.get("date"), race.get("track"), race.get("race_number"))
        if not key:
            continue
        program_races.add(key)
        for horse in horses:
            try:
                number = int(horse.get("number"))
            except (TypeError, ValueError):
                continue
            program_rows.append({
                "race_key": key,
                "horse_number": number,
                "jockey": first_value(horse, JOCKEY_KEYS),
                "trainer": first_value(horse, TRAINER_KEYS),
                "source_file": path.name,
            })

    matched_records: Any = []
    matched_load_error = None
    try:
        matched_records = json.loads(matched_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        matched_load_error = str(exc)
    if isinstance(matched_records, dict):
        for wrapper_key in ("matched_races", "races", "data"):
            if isinstance(matched_records.get(wrapper_key), list):
                matched_records = matched_records[wrapper_key]
                break
    if not isinstance(matched_records, list):
        matched_records = []

    verified_rows: list[dict[str, Any]] = []
    verified_races: set[str] = set()
    invalid_verified_records = 0
    matched_program_file_keys: set[str] = set()
    matched_record_count = 0

    for record in matched_records:
        if not isinstance(record, dict):
            continue
        match = record.get("match")
        status = norm_text(match.get("status")) if isinstance(match, dict) else ""
        confidence = match.get("confidence") if isinstance(match, dict) else None
        program = record.get("program")
        result = record.get("result")
        if status:
            # An explicit status is authoritative; do not override a mismatch.
            verified = status in {"MATCHED", "EXACT", "VERIFIED", "CONFIRMED"}
        elif confidence is not None:
            try:
                verified = float(confidence) >= 100
            except (TypeError, ValueError):
                verified = False
        else:
            verified = isinstance(program, dict) and isinstance(result, dict)
        if not verified or not isinstance(program, dict) or not isinstance(result, dict):
            continue
        matched_record_count += 1
        race = program.get("race") if isinstance(program.get("race"), dict) else {}
        key = race_key(
            program.get("date") or result.get("date"),
            race.get("track") or program.get("track") or result.get("track"),
            race.get("race_number") or result.get("race_number"),
        )
        if not key:
            invalid_verified_records += 1
            continue
        verified_races.add(key)
        source_program = program.get("source_file")
        if source_program:
            matched_program_file_keys.add(str(source_program))
        horses = program.get("horses")
        arrival = result.get("arrival")
        if not isinstance(horses, list) or not isinstance(arrival, list) or not arrival:
            invalid_verified_records += 1
            continue
        arrival_numbers = set()
        for item in arrival:
            try:
                n = int(item)
                if n > 0:
                    arrival_numbers.add(n)
            except (TypeError, ValueError):
                continue
        if not arrival_numbers:
            invalid_verified_records += 1
            continue
        for horse in horses:
            if not isinstance(horse, dict):
                continue
            try:
                number = int(horse.get("number"))
            except (TypeError, ValueError):
                continue
            verified_rows.append({
                "race_key": key,
                "horse_number": number,
                "jockey": first_value(horse, JOCKEY_KEYS),
                "trainer": first_value(horse, TRAINER_KEYS),
                "has_result_record": True,
                "horse_number_in_official_arrival": number in arrival_numbers,
            })

    # Link by race key + horse number; report coverage only for records actually joined.
    program_identity = {(r["race_key"], r["horse_number"]): r for r in program_rows}
    matched_identity = {(r["race_key"], r["horse_number"]): r for r in verified_rows}
    exact_identity_keys = set(program_identity) & set(matched_identity)
    linked_program_rows = [program_identity[k] for k in exact_identity_keys]
    linked_result_rows = [matched_identity[k] for k in exact_identity_keys]

    return {
        "audit_type": "jockey_trainer_coverage_only",
        "production_model_changed": False,
        "structured_programs": {
            "files_found": len(program_files),
            "malformed_files": malformed_program_files,
            "distinct_races": len(program_races),
            **_coverage(program_rows),
        },
        "verified_matched_records": {
            "records_with_program_and_result": matched_record_count,
            "distinct_races": len(verified_races),
            "runner_rows_with_result_record": len(verified_rows),
            "rows_with_horse_number_in_official_arrival": sum(r["horse_number_in_official_arrival"] for r in verified_rows),
            "invalid_or_incomplete_records": invalid_verified_records,
            **_coverage(verified_rows),
        },
        "exact_program_to_result_runner_linkage": {
            "distinct_program_races": len(program_races),
            "distinct_verified_result_races": len(verified_races),
            "race_keys_in_both_sets": len(program_races & verified_races),
            "program_runner_rows_linked_by_race_key_and_number": len(exact_identity_keys),
            "program_runner_rows_with_jockey_or_driver": sum(nonempty(r["jockey"]) for r in linked_program_rows),
            "program_runner_rows_with_trainer": sum(nonempty(r["trainer"]) for r in linked_program_rows),
            "verified_result_linked_rows_with_jockey_or_driver": sum(nonempty(r["jockey"]) for r in linked_result_rows),
            "verified_result_linked_rows_with_trainer": sum(nonempty(r["trainer"]) for r in linked_result_rows),
            "matched_source_program_files": len(matched_program_file_keys),
            "note": "A race-key/horse-number match is a linkage diagnostic, not proof that every source pairing is correct. Inspect duplicate keys and source provenance before feature use.",
        },
        "matched_file_error": matched_load_error,
        "notes": [
            "Audit only; no model training, prediction, or production feature files are modified.",
            "Jockey and trainer names are counted only when explicit structured fields are populated; free-text descriptions are not parsed.",
            "Verified result linkage follows the repository's current permissive convention that a record containing both program and result objects may count as matched when no explicit status is supplied.",
            "This report measures availability and linkage, not historical jockey/trainer performance. Any future performance rates must be walk-forward and exclude same-day outcomes.",
        ],
    }


if __name__ == "__main__":
    print(json.dumps(audit(), ensure_ascii=False, indent=2))
