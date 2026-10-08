from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[2]
PROGRAMS_DIR = BASE_DIR / "data" / "structured" / "programs"


def _as_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def load_program_history(exclude_on_or_after: str | None = None) -> list[dict[str, Any]]:
    """Load pre-race program participation for historical profiling only.

    These rows deliberately contain no outcome labels and are never used as
    supervised training targets. They only teach chronological start/course/
    distance recency features that were observable before a later race.
    """
    cutoff = _as_date(exclude_on_or_after) if exclude_on_or_after else None
    rows: list[dict[str, Any]] = []
    if not PROGRAMS_DIR.exists():
        return rows

    for path in sorted(PROGRAMS_DIR.glob("*.json")):
        try:
            program = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(program, dict):
            continue
        race = program.get("race") or {}
        d = _as_date(program.get("date"))
        track = race.get("track")
        race_number = race.get("race_number")
        if d is None or not track or race_number is None:
            continue
        if cutoff is not None and d >= cutoff:
            continue
        try:
            race_number = int(race_number)
        except (TypeError, ValueError):
            continue
        race_key = f"{d.isoformat()}|{str(track).strip().upper()}|{race_number}"
        for horse in program.get("horses") or []:
            if not isinstance(horse, dict):
                continue
            try:
                number = int(horse.get("number"))
            except (TypeError, ValueError):
                continue
            name = horse.get("horse")
            if not name:
                continue
            rows.append({
                "race_key": race_key,
                "date": d.isoformat(),
                "track": str(track).strip().upper(),
                "race_number": race_number,
                "race_name": race.get("race_name"),
                "race_type": race.get("race_type"),
                "distance": race.get("distance"),
                "runners_count": race.get("runners_count"),
                "prize_euros": race.get("prize_euros"),
                "horse_number": number,
                "horse_name": name,
                "horse_description": horse.get("description"),
                "_program_only_history": True,
            })
    return rows
