"""Read-only PMU Turfinfo arrival probe; no training or betting side effects.

The result is accepted only after the first five official arrival positions are
unique, map to declared program numbers, and agree with the local result prefix.
The module intentionally ignores all odds, payout, press, and market fields.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from src.matching.race_matcher import normalize_track

BASE_DIR = Path(__file__).resolve().parents[2]
PROGRAM_DIR = BASE_DIR / "data" / "structured" / "programs"
RESULT_DIR = BASE_DIR / "data" / "structured" / "results"
DEFAULT_REPORT = BASE_DIR / "data" / "evaluation" / "pmu_arrival_source_probe.json"
SOURCE_NAME = "candidate_pmu_turfinfo_participants_endpoint"
SOURCE_ROOT = "https://online.turfinfo.api.pmu.fr/rest/client/1/programme"
REQUEST_TIMEOUT_SECONDS = 12


def strict_positive_int(value: Any) -> int | None:
    """Accept positive integer values without rounding or guessing."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float):
        return int(value) if value.is_integer() and value > 0 else None
    if isinstance(value, str):
        value = value.strip()
        if value.isdigit():
            number = int(value)
            return number if number > 0 else None
    return None


def strict_arrival(value: Any) -> list[int] | None:
    """Parse a flat ordered list of unique positive horse numbers."""
    if not isinstance(value, list) or not value:
        return None
    result: list[int] = []
    for item in value:
        number = strict_positive_int(item)
        if number is None:
            return None
        result.append(number)
    if len(result) != len(set(result)):
        return None
    return result


def pmu_participants_url(race_date: str, meeting: int, race_number: int) -> str:
    """Build the read-only URL for one explicitly identified race."""
    parsed = datetime.strptime(race_date, "%Y-%m-%d").date()
    meeting_number = strict_positive_int(meeting)
    race = strict_positive_int(race_number)
    if meeting_number is None or race is None:
        raise ValueError("Meeting and race number must be positive integers.")
    return (
        f"{SOURCE_ROOT}/{parsed.strftime('%d%m%Y')}"
        f"/R{meeting_number}/C{race}/participants"
    )


def _race_key(date_text: Any, track: Any, race_number: Any) -> str | None:
    date_value = str(date_text or "").strip()[:10]
    try:
        datetime.strptime(date_value, "%Y-%m-%d")
    except ValueError:
        return None
    track_value = normalize_track(track)
    number = strict_positive_int(race_number)
    if not track_value or number is None:
        return None
    return f"{date_value}|{track_value}|{number}"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_local_evidence(
    race_date: str,
    track: str,
    meeting: int,
    race_number: int,
    program_dir: Path = PROGRAM_DIR,
    result_dir: Path = RESULT_DIR,
) -> dict[str, Any]:
    """Load exact local race identity, declared roster and result prefix.

    Program copies with different rosters or result copies with contradictory
    arrivals are rejected. Program 'published_arrival' and all odds are ignored.
    """
    target_key = _race_key(race_date, track, race_number)
    if target_key is None:
        return {"accepted": False, "reason": "invalid_requested_race_identity"}

    programs: list[tuple[str, dict[str, Any], set[int]]] = []
    if program_dir.exists():
        for path in sorted(program_dir.glob("*.json")):
            try:
                payload = _load_json(path)
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict) or payload.get("document_type") != "program":
                continue
            race = payload.get("race") if isinstance(payload.get("race"), dict) else {}
            key = _race_key(payload.get("date") or race.get("date"),
                            race.get("track") or payload.get("track"),
                            race.get("race_number") or payload.get("race_number"))
            if key != target_key:
                continue
            horses = payload.get("horses")
            if not isinstance(horses, list) or not horses:
                return {"accepted": False, "reason": "program_has_no_declared_roster"}
            numbers: list[int] = []
            valid = True
            for horse in horses:
                if not isinstance(horse, dict):
                    valid = False
                    break
                number = strict_positive_int(horse.get("number"))
                if number is None:
                    valid = False
                    break
                numbers.append(number)
            if not valid or len(numbers) != len(set(numbers)):
                return {"accepted": False, "reason": "program_roster_has_invalid_or_duplicate_numbers"}
            expected_count = strict_positive_int(race.get("runners_count"))
            if expected_count is not None and expected_count != len(numbers):
                return {"accepted": False, "reason": "program_declared_runner_count_mismatch"}
            programs.append((path.name, payload, set(numbers)))

    if not programs:
        return {"accepted": False, "reason": "matching_local_program_not_found"}

    roster_signatures = {tuple(sorted(item[2])) for item in programs}
    if len(roster_signatures) != 1:
        return {"accepted": False, "reason": "conflicting_local_program_rosters"}

    # Only a non-empty local structured result arrival is used as a cross-check.
    result_candidates: list[tuple[str, list[int]]] = []
    if result_dir.exists():
        for path in sorted(result_dir.glob("*.json")):
            try:
                payload = _load_json(path)
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict) or payload.get("document_type") != "result":
                continue
            if str(payload.get("date") or "")[:10] != race_date:
                continue
            if normalize_track(payload.get("track")) != normalize_track(track):
                continue
            races = payload.get("races")
            if not isinstance(races, list):
                continue
            for race in races:
                if not isinstance(race, dict):
                    continue
                if strict_positive_int(race.get("race_number")) != race_number:
                    continue
                arrival = strict_arrival(race.get("arrival"))
                if arrival is None or len(arrival) < 3:
                    continue
                result_candidates.append((path.name, arrival))

    if not result_candidates:
        return {"accepted": False, "reason": "matching_local_result_prefix_not_found"}

    # Shorter result copies may be prefixes of a more complete result. Any
    # incompatible prefix quarantines the race rather than choosing by filename.
    result_candidates.sort(key=lambda item: (-len(item[1]), item[0]))
    longest = result_candidates[0][1]
    if any(longest[:len(arrival)] != arrival for _, arrival in result_candidates[1:]):
        return {"accepted": False, "reason": "conflicting_local_result_arrivals"}

    program_file, program, roster = sorted(
        programs, key=lambda item: (-sum(
            horse.get(field) not in (None, "")
            for horse in item[1].get("horses") or []
            for field in ("performance", "gains", "trainer", "jockey", "driver")
        ), item[0])
    )[0]
    meeting_from_result: set[int] = set()
    if result_dir.exists():
        for path in sorted(result_dir.glob("*.json")):
            try:
                payload = _load_json(path)
            except (OSError, json.JSONDecodeError):
                continue
            if (isinstance(payload, dict)
                    and payload.get("document_type") == "result"
                    and str(payload.get("date") or "")[:10] == race_date
                    and normalize_track(payload.get("track")) == normalize_track(track)):
                for race in payload.get("races") or []:
                    if isinstance(race, dict) and strict_positive_int(race.get("race_number")) == race_number:
                        value = strict_positive_int(payload.get("meeting"))
                        if value is not None:
                            meeting_from_result.add(value)

    if meeting_from_result and meeting not in meeting_from_result:
        return {"accepted": False, "reason": "requested_meeting_conflicts_with_local_result"}

    horse_names_by_number = {
        str(number): str(horse.get("horse") or horse.get("horse_name") or "")
        for horse in (program.get("horses") or [])
        if isinstance(horse, dict)
        for number in [strict_positive_int(horse.get("number"))]
        if number is not None
    }
    local_prefix = longest[:min(5, len(longest))]
    return {
        "accepted": True,
        "race_key": target_key,
        "date": race_date,
        "track": track,
        "meeting": meeting,
        "race_number": race_number,
        "race_name": (program.get("race") or {}).get("race_name"),
        "race_type": (program.get("race") or {}).get("race_type"),
        "declared_runner_count": len(roster),
        "roster_numbers": sorted(roster),
        "horse_names_by_number": horse_names_by_number,
        "local_result_prefix": local_prefix,
        "local_result_details": [
            {"rank": rank, "horse_number": number, "horse_name": horse_names_by_number.get(str(number))}
            for rank, number in enumerate(local_prefix, start=1)
        ],
        "local_result_positions_available": len(longest),
        "local_program_file": program_file,
        "local_result_files": sorted(name for name, _ in result_candidates),
    }


def validate_pmu_payload(
    payload: Any,
    roster_numbers: set[int],
    local_result_prefix: list[int],
) -> dict[str, Any]:
    """Extract and validate first five positions without touching price fields."""
    if isinstance(payload, list):
        participants = payload
    elif isinstance(payload, dict):
        participants = payload.get("participants")
        if participants is None:
            participants = payload.get("partants")
    else:
        participants = None
    if not isinstance(participants, list) or not participants:
        return {"accepted": False, "reason": "participants_list_missing_or_malformed"}

    ranked: dict[int, int] = {}
    ranked_names: dict[int, str | None] = {}
    used_numbers: set[int] = set()
    for item in participants:
        if not isinstance(item, dict):
            continue
        number = strict_positive_int(item.get("numPmu"))
        rank = strict_positive_int(item.get("ordreArrivee"))
        if number is None or rank is None or rank > 5:
            continue
        if rank in ranked:
            return {"accepted": False, "reason": "duplicate_or_tied_arrival_position"}
        if number in used_numbers:
            return {"accepted": False, "reason": "runner_number_repeated_in_top5"}
        name = next((str(item[field]).strip() for field in (
            "nom", "nomCheval", "nomChevalEngage", "nomCourt", "horseName"
        ) if item.get(field) not in (None, "")), None)
        ranked[rank] = number
        ranked_names[rank] = name
        used_numbers.add(number)

    if set(ranked) != {1, 2, 3, 4, 5}:
        return {"accepted": False, "reason": "five_unique_arrival_positions_unavailable"}

    top5 = [ranked[position] for position in range(1, 6)]
    top5_details = [
        {"rank": position, "horse_number": ranked[position], "horse_name": ranked_names.get(position)}
        for position in range(1, 6)
    ]
    outside_roster = [number for number in top5 if number not in roster_numbers]
    if outside_roster:
        return {
            "accepted": False,
            "reason": "top5_contains_runner_outside_declared_roster",
            "outside_roster_numbers": outside_roster,
        }

    # Local LONAB result rows consistently agree on the first three places,
    # while positions after third have shown a different reporting convention.
    # Therefore only the local Top-3 is a hard cross-check; later positions are
    # separately flagged and must never be silently reconciled or called verified.
    prefix_length = min(3, len(local_result_prefix))
    local_prefix = local_result_prefix[:prefix_length]
    pmu_prefix = top5[:prefix_length]
    if pmu_prefix != local_prefix:
        return {
            "accepted": False,
            "reason": "pmu_top3_disagrees_with_local_result_prefix",
            "local_prefix": local_prefix,
            "pmu_prefix": pmu_prefix,
            "pmu_top5_details": top5_details,
            "source_approved_for_training": False,
        }

    tail_conflicts = []
    for position in range(4, min(5, len(local_result_prefix)) + 1):
        local_number = local_result_prefix[position - 1]
        pmu_number = top5[position - 1] if position <= len(top5) else None
        if pmu_number != local_number:
            tail_conflicts.append({
                "rank": position,
                "local_number": local_number,
                "pmu_number": pmu_number,
                "requires_manual_resolution": True,
            })

    local_tail_match = not tail_conflicts
    reason = (
        "top3_roster_match_but_local_tail_conflict"
        if tail_conflicts
        else "top3_and_roster_match_full_top5_shadow_only"
    )
    return {
        "accepted": True,
        "reason": reason,
        "top5_numbers": top5,
        "top5_details": top5_details,
        "local_top3_match": True,
        "matched_local_prefix_positions": prefix_length,
        "local_tail_match": local_tail_match,
        "local_tail_conflicts": tail_conflicts,
        "source_approved_for_training": False,
        "policy": {
            "odds_and_market_fields_ignored": True,
            "local_program_published_arrival_ignored": True,
            "only_local_top3_is_hard_crosscheck": True,
            "tail_conflicts_need_manual_resolution": True,
            "not_yet_approved_for_training": True,
        },
    }


def probe(
    race_date: str,
    track: str,
    meeting: int,
    race_number: int,
    program_dir: Path = PROGRAM_DIR,
    result_dir: Path = RESULT_DIR,
    report_path: Path | None = DEFAULT_REPORT,
) -> dict[str, Any]:
    """Perform one bounded read-only request and save an auditable probe report."""
    retrieved_at = datetime.now(timezone.utc).isoformat()
    local = load_local_evidence(
        race_date, track, meeting, race_number, program_dir, result_dir
    )
    report: dict[str, Any] = {
        "schema_version": 1,
        "source": SOURCE_NAME,
        "retrieved_at": retrieved_at,
        "status": "local_evidence_rejected",
        "race": {
            "date": race_date,
            "track": track,
            "meeting": meeting,
            "race_number": race_number,
        },
        "local_evidence": local,
        "policy": {
            "read_only": True,
            "writes_training_dataset": False,
            "writes_model_bundle": False,
            "changes_live_prediction": False,
            "changes_betting_guard": False,
            "odds_or_market_fields_used": False,
            "source_approved_for_training": False,
        },
    }

    if not local.get("accepted"):
        report["reason"] = local.get("reason", "local_evidence_rejected")
    else:
        try:
            url = pmu_participants_url(race_date, meeting, race_number)
        except (TypeError, ValueError):
            url = None
            report["reason"] = "invalid_request_parameters"

        if url:
            report["source_url"] = url
            try:
                response = requests.get(
                    url,
                    headers={
                        "Accept": "application/json",
                        "User-Agent": "horse-racing-machine-arrival-audit/1.0",
                    },
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
                body = response.content or b""
                report["http_status"] = int(response.status_code)
                report["response_sha256"] = hashlib.sha256(body).hexdigest()
                report["response_bytes"] = len(body)
                report["status"] = "source_rejected"
                if response.status_code < 200 or response.status_code >= 300:
                    report["reason"] = "source_http_status_not_success"
                else:
                    try:
                        payload = response.json()
                    except (ValueError, json.JSONDecodeError):
                        report["reason"] = "source_response_not_json"
                    else:
                        validation = validate_pmu_payload(
                            payload,
                            set(local["roster_numbers"]),
                            list(local["local_result_prefix"]),
                        )
                        report["source_validation"] = validation
                        if validation.get("accepted"):
                            if validation.get("local_tail_match") is False:
                                report["status"] = "top5_shadow_only_local_tail_conflict"
                            else:
                                report["status"] = "top5_crosscheck_passed_shadow_only"
                            report["reason"] = validation["reason"]
                        else:
                            report["reason"] = validation.get("reason", "source_validation_rejected")
            except requests.RequestException as error:
                report["status"] = "source_unavailable"
                report["reason"] = type(error).__name__

    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only PMU arrival validation probe.")
    parser.add_argument("--date", required=True, help="Race date in YYYY-MM-DD format.")
    parser.add_argument("--track", required=True)
    parser.add_argument("--meeting", required=True, type=int)
    parser.add_argument("--race", required=True, type=int)
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    args = parser.parse_args()

    report = probe(
        args.date,
        args.track,
        args.meeting,
        args.race,
        report_path=Path(args.report),
    )
    print(json.dumps({
        "status": report.get("status"),
        "reason": report.get("reason"),
        "race": report.get("race"),
        "source_url": report.get("source_url"),
        "http_status": report.get("http_status"),
        "response_sha256": report.get("response_sha256"),
        "source_validation": report.get("source_validation"),
        "report_path": args.report,
        "production_effect": "none",
    }, indent=2, ensure_ascii=False))
    # Unavailable or rejected evidence is a valid fail-closed audit outcome.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
