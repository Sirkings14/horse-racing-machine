from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from src.parsers.program_parser import parse_program_text
from src.processors.pdf_reader import read_pdf_file
from src.scraper import PROGRAM_URLS, download_pdf, get_pdf_links
from src.live.registry import LIVE_DIR, upsert_race


def _race_key(program: dict) -> str | None:
    race = program.get("race") or {}
    race_date = program.get("date") or race.get("date")
    track = race.get("track") or program.get("track")
    number = race.get("race_number") or program.get("race_number")
    if not race_date or not track or number is None:
        return None
    try:
        number = int(number)
    except (TypeError, ValueError):
        return None
    return f"{race_date}|{str(track).strip().upper()}|{number}"


def _is_eligible(program: dict, today: date) -> tuple[bool, str]:
    if program.get("document_type") != "program":
        return False, "wrong_document_type"
    race = program.get("race") or {}
    race_date = program.get("date") or race.get("date")
    if not race_date:
        return False, "missing_date"
    try:
        parsed_date = date.fromisoformat(str(race_date)[:10])
    except ValueError:
        return False, "invalid_date"
    if parsed_date < today:
        return False, "stale_program"
    track = race.get("track") or program.get("track")
    number = race.get("race_number") or program.get("race_number")
    horses = program.get("horses") or []
    expected = race.get("runners_count")
    if not track:
        return False, "missing_track"
    if number is None:
        return False, "missing_race_number"
    if not horses:
        return False, "missing_horses"
    numbers = [horse.get("number") for horse in horses]
    if len(numbers) != len(set(numbers)):
        return False, "duplicate_horse_numbers"
    if expected is not None and len(horses) != int(expected):
        return False, "runner_count_mismatch"
    if _race_key(program) is None:
        return False, "missing_race_key"
    return True, "validated"


def collect_live_programs() -> list[dict]:
    """Discover, parse, validate, and register only current/future program PDFs."""
    today = datetime.now(timezone.utc).date()
    live_raw = LIVE_DIR / "raw"
    live_structured = LIVE_DIR / "structured"
    live_raw.mkdir(parents=True, exist_ok=True)
    live_structured.mkdir(parents=True, exist_ok=True)

    discovered_urls: list[str] = []
    seen = set()
    for page_url in PROGRAM_URLS:
        try:
            for url in get_pdf_links(page_url, "program"):
                if url not in seen:
                    seen.add(url)
                    discovered_urls.append(url)
        except Exception as error:
            print(f"Live source failed: {page_url} | {error}")

    print(f"Live program PDFs discovered: {len(discovered_urls)}")
    validated = []

    for url in discovered_urls:
        try:
            path = download_pdf(url, str(live_raw), "live_program")
            if not path:
                continue
            pdf_path = Path(path)
            pdf_data = read_pdf_file(pdf_path)
            program = parse_program_text(pdf_data.get("text", ""), pdf_path.name)
            program["source_url"] = url
            program["source_domain"] = urlparse(url).netloc
            program["source_sha256"] = hashlib.sha256(pdf_path.read_bytes()).hexdigest()

            eligible, reason = _is_eligible(program, today)
            program["validation_status"] = "validated" if eligible else "rejected"
            program["validation_reason"] = reason
            key = _race_key(program)

            if not eligible or not key:
                print(f"Live program rejected: {pdf_path.name} | {reason}")
                continue

            output_path = live_structured / f"{key.replace('|', '_')}.json"
            output_path.write_text(json.dumps(program, ensure_ascii=False, indent=2), encoding="utf-8")

            race = program["race"]
            entry = {
                "race_key": key,
                "date": program.get("date"),
                "track": race.get("track"),
                "race_number": race.get("race_number"),
                "race_name": race.get("race_name"),
                "race_type": race.get("race_type"),
                "distance": race.get("distance"),
                "runners_count": race.get("runners_count"),
                "horse_count": len(program.get("horses") or []),
                "source_url": url,
                "source_file": pdf_path.name,
                "structured_file": str(output_path.relative_to(LIVE_DIR)),
                "status": "validated",
                "prediction_status": "pending",
                "discovered_at": datetime.now(timezone.utc).isoformat(),
            }
            upsert_race(entry)
            validated.append(program)
        except Exception as error:
            print(f"Live program failed: {url} | {error}")

    print(f"Live programs validated: {len(validated)}")
    return validated
