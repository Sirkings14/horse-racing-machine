"""Capture auditable pre-race PMU win-odds snapshots.

The PMU JSON endpoint used here is an undocumented public web feed, not a
supported public API. The adapter is deliberately conservative: a race must
match by venue, name, distance and field size; runner numbers and names must
match the live card; only timestamped direct win quotes are accepted; and no
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
MAX_LOOKAHEAD_MINUTES = 720
MIN_IDENTITY_COVERAGE = 0.80
MIN_PRICE_COVERAGE = 0.80
USER_AGENT = "horse-racing-machine/1.0 (low-rate pre-race odds evidence capture)"


def normalize_text(value: Any) -> str:
    """Normalize accents, punctuation and whitespace for conservative matching."""
    decomposed = unicodedata.normalize("NFKD", str(value or ""))
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return "".join(char for char in without_marks.upper() if char.isalnum())


def normalize_track(value: Any) -> str:
    """Normalize LONAB venue names against PMU's 'HIPPODROME DE ...' labels."""
    track = normalize_text(value)
    for prefix in ("HIPPODROMEDE", "HIPPODROMED"):
        if track.startswith(prefix):
            return track[len(prefix):]
    return track


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
    # Use course-specific identifiers only; generic num/numero fields also
    # occur on participant rows and could create false course matches.
    for key in ("numExterne", "numCourse", "numeroCourse", "courseNumber"):
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


def iter_pmu_courses(payload: Any, race_date: str | None = None) -> list[dict[str, Any]]:
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
        payload_date = str(payload.get("date") or "")[:10] if isinstance(payload, dict) else ""
        off_at = _parse_timestamp(off_value, race_date or payload_date or None)

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
    local_track = normalize_track(race.get("track"))
    source_track = normalize_track(course.get("track"))
    if not local_track or not source_track:
        return False

    # Some LONAB program editions abbreviate the venue as PARIS, with the
    # actual venue embedded in the race heading. Only resolve known explicit
    # venue names; otherwise fail closed. Remove that venue prefix before
    # comparing the actual race title to the PMU course title.
    resolved_from_paris_label = False
    if local_track == "PARIS":
        title = normalize_text(race.get("race_name"))
        known_venues = ("VINCENNES", "AUTEUIL", "LONGCHAMP", "SAINTCLOUD")
        local_track = next((venue for venue in known_venues if venue in title), "")
        resolved_from_paris_label = bool(local_track)
    if local_track != source_track:
        return False

    local_name = normalize_text(race.get("race_name"))
    if resolved_from_paris_label and local_name.startswith(local_track):
        local_name = local_name[len(local_track):]
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


def _current_win_quote(participant: dict[str, Any]) -> tuple[float, datetime | None] | None:
    """Extract only explicitly labelled current win quotes; never payouts/results."""
    winner_types = {"SIMPLEGAGNANT", "GAGNANT", "SG", "WINNER"}
    quote_fields = ("cote", "coteGagnant", "coteSimpleGagnant", "coteDirecteGagnant")
    timestamp_fields = ("dateCote", "dateMajCote", "dateMiseAJourCote", "coteTimestamp", "timestampCote")

    def parse_quote(record: Any, require_win_type: bool) -> tuple[float, datetime | None] | None:
        if isinstance(record, (int, float, str)) and not require_win_type:
            price = _as_positive_decimal(record)
            return (price, None) if price is not None else None
        if not isinstance(record, dict):
            return None
        if require_win_type:
            bet_type = normalize_text(record.get("typePari") or record.get("type") or "")
            if bet_type not in winner_types:
                return None
        raw_price = next((record.get(key) for key in quote_fields if record.get(key) is not None), None)
        price = _as_positive_decimal(raw_price)
        if price is None:
            return None
        raw_timestamp = next((record.get(key) for key in timestamp_fields if record.get(key) is not None), None)
        if raw_timestamp is None:
            return price, None
        parsed_timestamp = _parse_timestamp(raw_timestamp)
        if parsed_timestamp is None:
            return None
        return price, parsed_timestamp

    # Direct, clearly named current-quote properties are supported.
    direct = parse_quote(participant, require_win_type=False)
    if direct is not None and any(participant.get(key) is not None for key in quote_fields):
        return direct

    # In PMU participant responses, dernierRapportDirect is the latest direct
    # quote (rapport), while dernierRapportReference is a separate reference
    # quote. Accept only the direct quote with a recognized winner-market type
    # and an explicit source timestamp; never substitute the reference quote.
    direct_report = participant.get("dernierRapportDirect")
    if isinstance(direct_report, dict):
        bet_type = normalize_text(direct_report.get("typePari") or direct_report.get("type") or "")
        report_kind = normalize_text(direct_report.get("typeRapport") or "")
        if bet_type in winner_types and report_kind not in {"DEFINITIF", "FINAL", "RESULTAT", "PAYOUT", "OFFICIEL"}:
            price = _as_positive_decimal(direct_report.get("rapport"))
            raw_timestamp = direct_report.get("dateRapport") or direct_report.get("date_rapport")
            quote_time = _parse_timestamp(raw_timestamp) if raw_timestamp is not None else None
            if price is not None and quote_time is not None:
                return price, quote_time

    # Other explicit current-cote shapes may be supported where the market is
    # identified. Generic report/payout fields and reference prices are not.
    raw_quotes = participant.get("cotes")
    if isinstance(raw_quotes, list):
        matched = [
            quote for quote in (parse_quote(item, require_win_type=True) for item in raw_quotes)
            if quote is not None
        ]
        return matched[0] if len(matched) == 1 else None
    if isinstance(raw_quotes, dict):
        matched = []
        for market, value in raw_quotes.items():
            if normalize_text(market) not in winner_types:
                continue
            if isinstance(value, dict):
                quote = parse_quote({"typePari": market, **value}, require_win_type=True)
            else:
                quote = parse_quote(value, require_win_type=False)
            if quote is not None:
                matched.append(quote)
        return matched[0] if len(matched) == 1 else None
    return None


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

        quote = _current_win_quote(participant)
        if quote is None:
            continue
        price, quote_time = quote
        if quote_time and (quote_time > captured or quote_time > off_at):
            # Ignore a quote whose explicit timestamp is after observation
            # or after scheduled off-time.
            continue

        odds[str(number)] = price
        if quote_time:
            source_timestamps[str(number)] = quote_time.isoformat()

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
        # Per-runner quote-update timestamps are also preserved where supplied.
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

    source_courses = iter_pmu_courses(daily_program, race_date=race_day.isoformat())
    if not source_courses:
        print("PMU odds capture skipped: response did not contain safely parseable meeting/course cards.")
        return stats

    for race_key, program in cards:
        course = match_pmu_course(source_courses, program)
        if course is None:
            race_meta = program.get("race") or {}
            target_identity = {
                "track": race_meta.get("track"),
                "race_name": race_meta.get("race_name"),
                "distance": race_meta.get("distance"),
                "runners_count": race_meta.get("runners_count"),
                "horse_count": len(program.get("horses") or []),
            }
            candidate_summary = [
                {
                    "track": item.get("track"),
                    "race_name": item.get("race_name"),
                    "meeting_number": item.get("meeting_number"),
                    "course_number": item.get("course_number"),
                    "distance": item.get("distance"),
                    "runners_count": item.get("runners_count"),
                    "off_at": item.get("off_at").isoformat() if isinstance(item.get("off_at"), datetime) else None,
                }
                for item in source_courses[:40]
            ]
            print(f"PMU odds capture skipped for {race_key}: venue/course match was absent or ambiguous.")
            print(json.dumps({
                "diagnostic": "pmu_course_match_failure",
                "race_key": race_key,
                "target": target_identity,
                "parsed_pmu_course_count": len(source_courses),
                "parsed_pmu_courses_sample": candidate_summary,
            }, ensure_ascii=False))
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
