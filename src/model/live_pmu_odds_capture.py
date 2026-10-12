"""Capture auditable pre-race PMU win-odds snapshots.

The PMU JSON endpoint used here is an undocumented public web feed, not a
supported public API. The adapter is deliberately conservative: a race must
match by venue, name, distance and field size; runner numbers and names must
match the live card; only SIMPLE_GAGNANT direct reports are accepted; and no
snapshot is written at or after the scheduled off-time. Source failure or an
unknown response shape results in no evidence, never guessed prices.
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from datetime import date, datetime, time, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from src.live.registry import LIVE_DIR, load_manifest
from src.model.market_evidence import append_snapshot

PMU_API_ROOT = "https://online.turfinfo.api.pmu.fr/rest/client/61"
SOURCE_LABEL = "PMU public live JSON (undocumented)"
PARIS_TZ = ZoneInfo("Europe/Paris")
MAX_LOOKAHEAD_MINUTES = 360
MIN_IDENTITY_COVERAGE = 0.80
MIN_PRICE_COVERAGE = 0.80
USER_AGENT = "horse-racing-machine/1.0 (low-rate pre-race odds evidence capture)"


def normalize_text(value: Any) -> str:
    """Normalize accents, punctuation and whitespace for conservative matching."""
    decomposed = unicodedata.normalize("NFKD", str(value or ""))
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return "".join(char for char in without_marks.upper() if char.isalnum())


def _first_text(payload: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            for nested_key in ("libelleLong", "libelleCourt", "libelle", "nom", "name", "code"):
                nested = value.get(nested_key)
                if isinstance(nested, str) and nested.strip():
                    return nested.strip()
    return None


def _as_int(value: Any) -> int | None:
    try:
        if isinstance(value, bool) or value is None:
            return None
        return int(float(str(value).strip()))
    except (TypeError, ValueError, OverflowError):
        return None


def _parse_timestamp(value: Any, race_date: str | None = None) -> datetime | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        numeric = float(value)
        # PMU JSON variants have used Unix seconds and milliseconds.
        if numeric > 10_000_000_000:
            numeric /= 1000.0
        try:
            return datetime.fromtimestamp(numeric, tz=timezone.utc)
        except (ValueError, OverflowError, OSError):
            return None
    if not isinstance(value, str) or not value.strip():
        return None

    value = value.strip()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            parsed = parsed.replace(tzinfo=PARIS_TZ)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        pass

    if race_date:
        for fmt in ("%H:%M:%S", "%H:%M"):
            try:
                parsed_time = datetime.strptime(value, fmt).time()
                parsed_date = date.fromisoformat(race_date[:10])
                return datetime.combine(parsed_date, parsed_time, tzinfo=PARIS_TZ).astimezone(timezone.utc)
            except ValueError:
                continue
    return None


def _course_number(node: dict[str, Any]) -> int | None:
    for key in ("numExterne", "numOrdre", "numCourse", "numeroCourse", "courseNumber", "numero", "num"):
        value = _as_int(node.get(key))
        if value is not None and 1 <= value <= 30:
            return value
    return None


def _meeting_number(node: dict[str, Any], inherited: int | None) -> int | None:
    for key in ("numReunion", "numeroReunion", "num_reunion", "numero_reunion"):
        value = _as_int(node.get(key))
        if value is not None and 1 <= value <= 30:
            return value
    if any(isinstance(node.get(key), list) for key in ("courses", "course")):
        value = _as_int(node.get("numOfficiel"))
        if value is not None and 1 <= value <= 30:
            return value
    return inherited


def iter_pmu_courses(payload: Any) -> list[dict[str, Any]]:
    """Extract course cards while inheriting venue and meeting identifiers."""
    found: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()

    def walk(node: Any, context: dict[str, Any]) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item, context)
            return
        if not isinstance(node, dict):
            return

        next_context = dict(context)
        track = _first_text(node, (
            "nomHippodrome", "libelleHippodrome", "hippodrome", "nomLieu", "venue",
        ))
        if track:
            next_context["track"] = track

        meeting = _meeting_number(node, _as_int(next_context.get("meeting_number")))
        if meeting is not None:
            next_context["meeting_number"] = meeting

        course_name = _first_text(node, (
            "libelleCourse", "nomCourse", "intitule", "libelle", "prix", "nom",
        ))
        course_number = _course_number(node)
        off_value = None
        for key in ("heureDepart", "heure_depart", "dateDepart", "date_depart", "offTime", "startTime"):
            if node.get(key) is not None:
                off_value = node.get(key)
                break
        source_track = track or next_context.get("track")
        meeting_number = meeting or _as_int(next_context.get("meeting_number"))
        race_date = str(payload.get("date") or "")[:10] if isinstance(payload, dict) else ""
        off_at = _parse_timestamp(off_value, race_date or None)

        # Do not yield records until the source provides all identifiers required
        # to build a precise Rn/Cn endpoint and a scheduled off-time.
        if course_name and course_number and meeting_number and source_track and off_at:
            distance = None
            for key in ("distance", "distanceMetre", "distanceMetres", "distance_m"):
                distance = _as_int(node.get(key))
                if distance is not None:
                    break
            runner_count = None
            for key in ("nombrePartants", "nbPartants", "nombre_partants", "partants"):
                runner_count = _as_int(node.get(key))
                if runner_count is not None:
                    break
            record = {
                "track": source_track,
                "race_name": course_name,
                "meeting_number": meeting_number,
                "course_number": course_number,
                "off_at": off_at,
                "distance": distance,
                "runners_count": runner_count,
            }
            identity = (
                record["track"], normalize_text(record["race_name"]),
                record["meeting_number"], record["course_number"], record["off_at"].isoformat(),
            )
            if identity not in seen:
                seen.add(identity)
                found.append(record)

        for child in node.values():
            if isinstance(child, (dict, list)):
                walk(child, next_context)

    walk(payload, {})
    return found


def course_matches_program(course: dict[str, Any], program: dict[str, Any]) -> bool:
    race = program.get("race") or {}
    local_track = normalize_text(race.get("track"))
    source_track = normalize_text(course.get("track"))
    if not local_track or not source_track:
        return False

    # Some LONAB program editions abbreviate the venue as PARIS, with the
    # actual venue embedded in the race heading. Only resolve known explicit
    # venue names; otherwise fail closed.
    if local_track == "PARIS":
        title = normalize_text(race.get("race_name"))
        known_venues = ("VINCENNES", "AUTEUIL", "LONGCHAMP", "SAINTCLOUD")
        local_track = next((venue for venue in known_venues if venue in title), "")
    if local_track != source_track:
        return False

    local_name = normalize_text(race.get("race_name"))
    source_name = normalize_text(course.get("race_name"))
    if not local_name or not source_name:
        return False
    name_match = (
        local_name == source_name
        or (min(len(local_name), len(source_name)) >= 9 and
            (local_name in source_name or source_name in local_name))
        or SequenceMatcher(None, local_name, source_name).ratio() >= 0.88
    )
    if not name_match:
        return False

    local_distance = _as_int(race.get("distance"))
    source_distance = _as_int(course.get("distance"))
    if local_distance and source_distance and local_distance != source_distance:
        return False

    local_runners = _as_int(race.get("runners_count")) or len(program.get("horses") or [])
    source_runners = _as_int(course.get("runners_count"))
    if local_runners and source_runners and local_runners != source_runners:
        return False

    return True


def match_pmu_course(courses: list[dict[str, Any]], program: dict[str, Any]) -> dict[str, Any] | None:
    matches = [course for course in courses if course_matches_program(course, program)]
    return matches[0] if len(matches) == 1 else None


def _direct_win_report(participant: dict[str, Any]) -> dict[str, Any] | None:
    report = participant.get("dernierRapportDirect")
    if isinstance(report, list):
        eligible = []
        for item in report:
            if not isinstance(item, dict):
                continue
            bet_type = normalize_text(item.get("typePari"))
            if not bet_type or bet_type in {"SIMPLEGAGNANT", "GAGNANT", "SG", "WINNER"}:
                eligible.append(item)
        report = eligible[0] if eligible else None
    if not isinstance(report, dict):
        return None
    bet_type = normalize_text(report.get("typePari"))
    if bet_type and bet_type not in {"SIMPLEGAGNANT", "GAGNANT", "SG", "WINNER"}:
        return None
    return report


def build_snapshot(
    race_key: str,
    program: dict[str, Any],
    course: dict[str, Any],
    participants_payload: Any,
    now: datetime,
) -> dict[str, Any] | None:
    """Build a strict, pre-off win-market snapshot from matching source runners."""
    if now.tzinfo is None or now.utcoffset() is None:
        return None
    captured = now.astimezone(timezone.utc)
    off_at = course.get("off_at")
    if not isinstance(off_at, datetime) or off_at.tzinfo is None or off_at.utcoffset() is None:
        return None
    off_at = off_at.astimezone(timezone.utc)
    if captured >= off_at:
        return None

    participants = None
    if isinstance(participants_payload, dict):
        for key in ("participants", "partants"):
            if isinstance(participants_payload.get(key), list):
                participants = participants_payload[key]
                break
    elif isinstance(participants_payload, list):
        participants = participants_payload
    if not participants:
        return None

    local_horses: dict[int, dict[str, Any]] = {}
    for horse in program.get("horses") or []:
        if not isinstance(horse, dict):
            continue
        number = _as_int(horse.get("number"))
        name = normalize_text(horse.get("horse"))
        if number and name:
            local_horses[number] = {"name": name, "source": horse}

    odds: dict[str, float] = {}
    source_timestamps: dict[str, str] = {}
    matched_identity: set[int] = set()

    for participant in participants:
        if not isinstance(participant, dict):
            continue
        number = _as_int(participant.get("numPmu") or participant.get("number") or participant.get("num"))
        if number not in local_horses:
            continue
        participant_name = normalize_text(participant.get("nom") or participant.get("horse") or participant.get("name"))
        if not participant_name:
            continue
        local_name = local_horses[number]["name"]
        if participant_name != local_name and SequenceMatcher(None, participant_name, local_name).ratio() < 0.90:
            continue
        matched_identity.add(number)

        status = normalize_text(participant.get("statut") or participant.get("status"))
        if status in {"NP", "NONPARTANT", "FORFAIT", "SCRATCHED"}:
            continue

        report = _direct_win_report(participant)
        if report is None:
            continue
        price = _as_positive_decimal(report.get("rapport"))
        if price is None:
            continue

        report_time = _parse_timestamp(report.get("dateRapport") or report.get("date_rapport"))
        if report_time and (report_time > captured or report_time > off_at):
            # Ignore a source record whose own timestamp is after observation
            # or after the scheduled off-time.
            continue

        odds[str(number)] = price
        if report_time:
            source_timestamps[str(number)] = report_time.isoformat()

    total_horses = len(local_horses)
    if total_horses == 0:
        return None
    if len(matched_identity) / total_horses < MIN_IDENTITY_COVERAGE:
        return None
    if len(odds) / total_horses < MIN_PRICE_COVERAGE:
        return None

    captured_iso = captured.isoformat()
    participants_url = course.get("participants_url")
    if not isinstance(participants_url, str) or not participants_url.startswith("https://"):
        return None

    return {
        "race_key": race_key,
        "captured_at": captured_iso,
        # This is the timestamp at which the current PMU response was observed.
        # Per-runner PMU dateRapport timestamps are also preserved where supplied.
        "price_timestamp": captured_iso,
        "race_off_at": off_at.isoformat(),
        "source": SOURCE_LABEL,
        "source_type": "tote_win",
        "market_type": "winner",
        "odds": odds,
        "runner_price_timestamps": source_timestamps,
        "source_url": participants_url,
        "raw_reference": participants_url,
    }


def _as_positive_decimal(value: Any) -> float | None:
    try:
        price = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return price if price > 1.0 else None


def fetch_json(url: str, timeout: float = 12.0) -> Any:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"PMU endpoint returned HTTP {response.status}")
        return json.loads(response.read().decode("utf-8"))


def _programme_url(race_day: date) -> str:
    date_code = race_day.strftime("%d%m%Y")
    return f"{PMU_API_ROOT}/programme/{date_code}?specialisation=INTERNET"


def _participants_url(race_day: date, meeting_number: int, course_number: int) -> str:
    date_code = race_day.strftime("%d%m%Y")
    query = urlencode({"specialisation": "INTERNET"})
    return (
        f"{PMU_API_ROOT}/programme/{date_code}/R{meeting_number}/C{course_number}/participants"
        f"?{query}"
    )


def _live_cards_for_day(race_day: date) -> list[tuple[str, dict[str, Any]]]:
    manifest = load_manifest()
    cards = []
    for entry in manifest.get("races", []):
        if not isinstance(entry, dict) or entry.get("status") != "validated":
            continue
        if str(entry.get("date") or "")[:10] != race_day.isoformat():
            continue
        if entry.get("result_status") == "verified":
            continue
        structured_file = entry.get("structured_file")
        if not isinstance(structured_file, str) or not structured_file.strip():
            continue
        path = LIVE_DIR / structured_file
        try:
            program = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(program, dict) and program.get("document_type") == "program":
            cards.append((str(entry.get("race_key") or ""), program))
    return cards


def collect_for_day(race_day: date | None = None, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Capture time must be timezone-aware.")
    now = now.astimezone(timezone.utc)
    race_day = race_day or now.date()
    cards = _live_cards_for_day(race_day)
    stats = {"race_day": race_day.isoformat(), "cards_today": len(cards), "matched": 0, "snapshots_added": 0, "skipped": 0}

    if not cards:
        print("PMU odds capture skipped: no validated LONAB program card for this date.")
        return stats

    try:
        daily_program = fetch_json(_programme_url(race_day))
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, RuntimeError) as error:
        print(f"PMU odds capture unavailable: daily program request failed: {error}")
        return stats

    source_courses = iter_pmu_courses(daily_program)
    if not source_courses:
        print("PMU odds capture skipped: response did not contain safely parseable meeting/course cards.")
        return stats

    for race_key, program in cards:
        course = match_pmu_course(source_courses, program)
        if course is None:
            print(f"PMU odds capture skipped for {race_key}: venue/course match was absent or ambiguous.")
            stats["skipped"] += 1
            continue

        off_at = course.get("off_at")
        if not isinstance(off_at, datetime):
            stats["skipped"] += 1
            continue
        minutes_to_off = (off_at.astimezone(timezone.utc) - now).total_seconds() / 60.0
        if minutes_to_off <= 0:
            print(f"PMU odds capture skipped for {race_key}: scheduled off-time has passed.")
            stats["skipped"] += 1
            continue
        if minutes_to_off > MAX_LOOKAHEAD_MINUTES:
            print(f"PMU odds capture deferred for {race_key}: {minutes_to_off:.0f} minutes to off.")
            continue

        meeting_number = _as_int(course.get("meeting_number"))
        course_number = _as_int(course.get("course_number"))
        if not meeting_number or not course_number:
            stats["skipped"] += 1
            continue

        participants_url = _participants_url(race_day, meeting_number, course_number)
        course = {**course, "participants_url": participants_url}
        try:
            participants_payload = fetch_json(participants_url)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, RuntimeError) as error:
            print(f"PMU odds capture unavailable for {race_key}: participants request failed: {error}")
            stats["skipped"] += 1
            continue

        snapshot = build_snapshot(race_key, program, course, participants_payload, now)
        if snapshot is None:
            print(f"PMU odds capture skipped for {race_key}: runner identity, prices or pre-off evidence was insufficient.")
            stats["skipped"] += 1
            continue

        stats["matched"] += 1
        if append_snapshot(snapshot):
            stats["snapshots_added"] += 1
            print(f"Captured pre-race PMU win-odds snapshot for {race_key}: {len(snapshot['odds'])}/{len(program.get('horses') or [])} runners priced.")
        else:
            print(f"PMU odds snapshot not added for {race_key}: duplicate or rejected evidence.")

    print(json.dumps(stats, ensure_ascii=False))
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="Race date in YYYY-MM-DD format; defaults to UTC today.")
    args = parser.parse_args()
    try:
        race_day = date.fromisoformat(args.date) if args.date else None
        collect_for_day(race_day=race_day)
    except (ValueError, OSError) as error:
        parser.error(str(error))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
