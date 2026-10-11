"""Add recent locally stored race results only after strict roster/result verification.

This module is intentionally offline. It never consumes a program's
`published_arrival`, press rankings, or press-odds fields as labels or model
features. It emits Top-5 labels only when five official arrival positions are
available; otherwise Top-5 is unknown for every runner in that race.
"""
from __future__ import annotations

import ast
import json
import math
import unicodedata
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from src.learning.result_truth import canonical_key, validate_arrival
from src.model.race_type import canonical_race_type


BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_PROGRAM_DIR = BASE_DIR / "data" / "structured" / "programs"
DEFAULT_RESULT_DIR = BASE_DIR / "data" / "structured" / "results"
DEFAULT_AUDIT_FILE = BASE_DIR / "data" / "dataset" / "recent_supplement_audit.json"

PRE_RACE_FIELDS = (
    "horse", "horse_name", "performance", "gains", "sex", "age", "weight",
    "draw", "listed_chrono", "listed_distance", "trainer", "jockey", "driver", "owner",
)


def _parse_iso_date(value: Any) -> str | None:
    text = str(value or "").strip()[:10]
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return None


def _safe_int(value: Any) -> int | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        numeric = float(str(value).replace(",", "."))
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(numeric) or not numeric.is_integer():
        return None
    return int(numeric)


def _safe_float(value: Any) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        numeric = float(str(value).replace(",", "."))
    except (TypeError, ValueError, OverflowError):
        return None
    return numeric if math.isfinite(numeric) else None


def strict_arrival(value: Any) -> list[int] | None:
    """Parse a flat list of positive, integral horse numbers; reject ambiguity."""
    raw = value
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        try:
            raw = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            try:
                raw = ast.literal_eval(text)
            except (ValueError, SyntaxError):
                return None
    if not isinstance(raw, list) or not raw:
        return None
    result: list[int] = []
    for item in raw:
        if isinstance(item, (list, dict, tuple)) or isinstance(item, bool):
            return None
        number = _safe_int(item)
        if number is None or number <= 0:
            return None
        result.append(number)
    return result


def _normal_value(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.upper().strip().split())


def _program_numbers(program: dict[str, Any]) -> tuple[set[int] | None, str | None]:
    raw_horses = program.get("horses")
    if not isinstance(raw_horses, list) or not raw_horses:
        return None, "empty_program_roster"
    numbers: list[int] = []
    for horse in raw_horses:
        if not isinstance(horse, dict):
            return None, "malformed_runner_record"
        number = _safe_int(horse.get("number"))
        if number is None or number <= 0:
            return None, "runner_number_missing_or_invalid"
        numbers.append(number)
    if len(numbers) != len(set(numbers)):
        return None, "duplicate_program_runner_number"
    return set(numbers), None


def _program_quality(program: dict[str, Any]) -> int:
    count = 0
    for horse in program.get("horses") or []:
        if not isinstance(horse, dict):
            continue
        count += sum(horse.get(field) not in (None, "") for field in PRE_RACE_FIELDS)
    return count


def _program_content_conflict(candidates: list[tuple[str, dict[str, Any]]]) -> str | None:
    """Fail closed if duplicated copies disagree on a non-empty runner field."""
    by_number: dict[int, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for _, program in candidates:
        for horse in program.get("horses") or []:
            if not isinstance(horse, dict):
                continue
            number = _safe_int(horse.get("number"))
            if number is None:
                continue
            for field in PRE_RACE_FIELDS:
                value = horse.get(field)
                if value not in (None, ""):
                    by_number[number][field].add(_normal_value(value))
    for number in sorted(by_number):
        for field in PRE_RACE_FIELDS:
            values = by_number[number].get(field) or set()
            if len(values) > 1:
                return f"conflicting_program_field:{number}:{field}"
    return None


def rows_from_verified_race(
    program: dict[str, Any],
    race_key: str,
    arrival: list[int],
    truth_validation: dict[str, Any],
    program_source: str,
    result_source: str,
) -> list[dict[str, Any]]:
    """Create rows from a complete declared field and a verified official arrival."""
    race = program.get("race") if isinstance(program.get("race"), dict) else {}
    horses = program.get("horses") or []
    if len(arrival) < 3 or truth_validation.get("accepted_for_learning") is not True:
        return []
    roster_numbers, roster_error = _program_numbers(program)
    if roster_error or not roster_numbers:
        return []
    if len(roster_numbers) != len(horses):
        return []
    declared = _safe_int(race.get("runners_count"))
    if declared is not None and declared > 0 and declared != len(roster_numbers):
        return []
    if not set(arrival).issubset(roster_numbers) or len(arrival) != len(set(arrival)):
        return []

    positions = {number: position for position, number in enumerate(arrival, start=1)}
    top3_numbers = set(arrival[:3])
    top4_labels_known = len(arrival) >= 4
    top5_labels_known = len(arrival) >= 5
    top4_numbers = set(arrival[:4]) if top4_labels_known else set()
    top5_numbers = set(arrival[:5]) if top5_labels_known else set()
    date_text = _parse_iso_date(program.get("date") or race.get("date"))
    track = race.get("track") or program.get("track")
    race_number = _safe_int(race.get("race_number"))
    if not date_text or not track or race_number is None:
        return []

    output = []
    for horse in horses:
        number = _safe_int(horse.get("number"))
        if number is None:
            return []
        position = positions.get(number)
        output.append({
            "race_key": race_key,
            "date": date_text,
            "track": track,
            "race_number": race_number,
            "race_name": race.get("race_name"),
            "race_type": canonical_race_type(race.get("race_type")),
            "distance": _safe_int(race.get("distance")),
            "runners_count": len(roster_numbers),
            "prize_euros": _safe_float(race.get("prize_euros")),
            "going": race.get("going"),
            "surface": race.get("surface"),
            "start_method": race.get("start_method") or race.get("start_type"),
            "track_condition": race.get("track_condition"),
            "horse_number": number,
            "horse_name": horse.get("horse") or horse.get("horse_name"),
            "horse_id": next((horse.get(k) for k in (
                "horse_id", "horseId", "horse_uid", "horseUid", "idCheval", "id_cheval",
                "identifiantCheval", "identifiant_cheval"
            ) if horse.get(k) not in (None, "")), None),
            "sex": horse.get("sex"),
            "age": _safe_int(horse.get("age")),
            "weight": _safe_float(horse.get("weight") if horse.get("weight") not in (None, "") else horse.get("poids")),
            "draw": _safe_int(horse.get("draw") if horse.get("draw") not in (None, "") else horse.get("corde")),
            "performance": horse.get("performance") or horse.get("recent_form") or horse.get("musique"),
            "gains": _safe_float(horse.get("gains")),
            "listed_chrono": horse.get("listed_chrono"),
            "listed_distance": horse.get("listed_distance"),
            "trainer": horse.get("trainer") or horse.get("entraineur"),
            "jockey": horse.get("jockey"),
            "driver": horse.get("driver"),
            "owner": horse.get("owner"),
            "finish_position": position,
            "won": int(number == arrival[0]),
            "top3": int(number in top3_numbers),
            "top4": int(number in top4_numbers) if top4_labels_known else None,
            # A partial arrival cannot define Top-5 negatives. Mask the entire
            # race's Top-5 labels to avoid selection-biased positive-only learning.
            "top5": int(number in top5_numbers) if top5_labels_known else None,
            "target_label_status": {
                "winner_known": True,
                "top3_known": True,
                "top4_known": top4_labels_known,
                "top5_known": top5_labels_known,
                "official_arrival_positions": len(arrival),
            },
            "truth_validation": truth_validation,
            "result_truth_verified": True,
            "data_source": "repo_structured_program_and_verified_result",
            "source_program": program_source,
            "source_result": result_source,
        })
    return output


def collect_recent_verified_rows(
    base_rows: list[dict[str, Any]],
    after_date: str,
    program_index: dict[str, dict[str, Any]],
    program_dir: Path = DEFAULT_PROGRAM_DIR,
    result_dir: Path = DEFAULT_RESULT_DIR,
    audit_path: Path | None = DEFAULT_AUDIT_FILE,
    as_of_date: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Supplement rows strictly after the base dataset cutoff, failing closed."""
    cutoff = _parse_iso_date(after_date)
    today = _parse_iso_date(as_of_date or date.today().isoformat())
    if cutoff is None or today is None:
        raise ValueError("Recent-supplement cutoff and as-of date must be valid ISO dates.")
    if cutoff >= today:
        return [], {
            "status": "no_supplement_window",
            "cutoff_date": cutoff,
            "as_of_date": today,
            "supplemented_races": 0,
            "supplemented_runner_rows": 0,
        }

    known_keys = {
        key for row in base_rows
        if (key := canonical_key(row.get("date"), row.get("track"), row.get("race_number")))
    }
    audit: dict[str, Any] = {
        "schema_version": 1,
        "status": "audit_only",
        "cutoff_date": cutoff,
        "as_of_date": today,
        "program_files_seen": 0,
        "program_races_after_cutoff": 0,
        "result_files_seen": 0,
        "result_races_seen": 0,
        "recent_result_races_seen": 0,
        "validated_result_records": 0,
        "duplicate_result_records": 0,
        "conflicting_result_races": 0,
        "rejected_result_records": 0,
        "missing_complete_program_races": 0,
        "program_content_conflicts": 0,
        "supplemented_races": 0,
        "supplemented_runner_rows": 0,
        "top5_label_complete_races": 0,
        "top5_label_incomplete_races": 0,
        "last_supplemented_date": None,
        "rejection_reasons": {},
        "ignored_fields": ["published_arrival", "rankings", "press_odds"],
        "policy": {
            "strict_date_track_race_key": True,
            "official_result_must_validate_against_complete_declared_roster": True,
            "conflicting_or_ambiguous_records_are_excluded": True,
            "top5_unknown_when_fewer_than_five_arrival_positions": True,
            "post_race_program_fields_are_never_used_as_labels": True,
        },
    }

    def reject(reason: str) -> None:
        reasons = audit["rejection_reasons"]
        reasons[reason] = reasons.get(reason, 0) + 1

    program_groups: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    if program_dir.exists():
        for path in sorted(program_dir.glob("*.json")):
            audit["program_files_seen"] += 1
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                reject("unreadable_program_json")
                continue
            if not isinstance(payload, dict) or payload.get("document_type") != "program":
                continue
            race = payload.get("race") if isinstance(payload.get("race"), dict) else {}
            race_date = _parse_iso_date(payload.get("date") or race.get("date"))
            race_number = _safe_int(race.get("race_number"))
            key = canonical_key(race_date, race.get("track") or payload.get("track"), race_number)
            if not race_date or race_date <= cutoff or race_date > today or not key or key in known_keys:
                continue
            audit["program_races_after_cutoff"] += 1
            meta = program_index.get(key)
            if not meta or meta.get("conflict") or not meta.get("horse_numbers"):
                reject("program_roster_missing_or_conflicting")
                continue
            numbers, number_error = _program_numbers(payload)
            if number_error:
                reject(number_error)
                continue
            expected = {int(value) for value in meta.get("horse_numbers") or []}
            if numbers != expected:
                reject("program_roster_mismatch")
                continue
            declared = _safe_int(race.get("runners_count"))
            if declared is not None and declared > 0 and declared != len(expected):
                reject("declared_runner_count_mismatch")
                continue
            program_groups[key].append((path.name, payload))

    result_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    blocked_keys: dict[str, str] = {}
    if result_dir.exists():
        for path in sorted(result_dir.glob("*.json")):
            audit["result_files_seen"] += 1
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                reject("unreadable_result_json")
                continue
            if not isinstance(payload, dict) or payload.get("document_type") != "result":
                continue
            result_date = _parse_iso_date(payload.get("date"))
            track = payload.get("track")
            if not result_date or not track or result_date <= cutoff or result_date > today:
                continue
            races = payload.get("races")
            if not isinstance(races, list):
                reject("invalid_result_races_list")
                continue
            for race in races:
                audit["result_races_seen"] += 1
                if not isinstance(race, dict):
                    reject("malformed_result_race")
                    continue
                race_number = _safe_int(race.get("race_number"))
                key = canonical_key(result_date, track, race_number)
                if not key or key in known_keys:
                    continue
                audit["recent_result_races_seen"] += 1
                arrival = strict_arrival(race.get("arrival"))
                if arrival is None:
                    blocked_keys[key] = "invalid_or_ambiguous_arrival_format"
                    audit["rejected_result_records"] += 1
                    reject("invalid_or_ambiguous_arrival_format")
                    continue
                truth = validate_arrival(key, arrival, program_index)
                if truth.get("accepted_for_learning") is not True:
                    blocked_keys[key] = str(truth.get("reason") or "result_truth_rejected")
                    audit["rejected_result_records"] += 1
                    reject(blocked_keys[key])
                    continue
                result_groups[key].append({
                    "source": path.name,
                    "arrival": arrival,
                    "truth": truth,
                    "date": result_date,
                })
                audit["validated_result_records"] += 1

    added_rows: list[dict[str, Any]] = []
    for key in sorted(set(result_groups) | set(blocked_keys)):
        if key in blocked_keys:
            continue
        candidates = result_groups.get(key) or []
        if not candidates:
            continue
        # Shorter official result extracts are compatible only if they are an
        # exact prefix of the longest one. Any contradictory place order blocks
        # the entire race rather than choosing a file arbitrarily.
        ordered = sorted(candidates, key=lambda item: (-len(item["arrival"]), item["source"]))
        longest = ordered[0]["arrival"]
        if any(longest[:len(item["arrival"])] != item["arrival"] for item in ordered[1:]):
            audit["conflicting_result_races"] += 1
            reject("conflicting_result_arrivals")
            continue
        if len(candidates) > 1:
            audit["duplicate_result_records"] += len(candidates) - 1

        program_candidates = program_groups.get(key) or []
        if not program_candidates:
            audit["missing_complete_program_races"] += 1
            reject("matching_complete_program_unavailable")
            continue
        content_conflict = _program_content_conflict(program_candidates)
        if content_conflict:
            audit["program_content_conflicts"] += 1
            reject(content_conflict)
            continue
        program_source, program = sorted(
            program_candidates,
            key=lambda item: (-_program_quality(item[1]), item[0]),
        )[0]
        result_source = ordered[0]["source"]
        truth = ordered[0]["truth"]
        race_rows = rows_from_verified_race(
            program, key, longest, truth, program_source, result_source
        )
        if not race_rows:
            reject("verified_race_row_build_failed")
            continue
        added_rows.extend(race_rows)
        audit["supplemented_races"] += 1
        audit["supplemented_runner_rows"] += len(race_rows)
        if len(longest) >= 5:
            audit["top5_label_complete_races"] += 1
        else:
            audit["top5_label_incomplete_races"] += 1
        audit["last_supplemented_date"] = max(
            str(audit["last_supplemented_date"] or ""), str(race_rows[0]["date"])
        )
    audit["status"] = "supplemented" if added_rows else "no_eligible_recent_races"
    if audit_path is not None:
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
    return added_rows, audit
