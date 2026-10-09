from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any


def normalize_person_or_horse(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.upper().replace("’", "'")
    return re.sub(r"[^A-Z0-9]+", "", text)


def normalize_track(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.upper().replace("’", "'")
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    tokens = [t for t in text.split() if t not in {"NOCTURNE", "EVENTARD"}]
    return " ".join(tokens).strip()


def _race_number(program: dict[str, Any]) -> int | None:
    try:
        return int((program.get("race") or {}).get("race_number"))
    except (TypeError, ValueError):
        return None


def _date(program: dict[str, Any]) -> str:
    return str(program.get("date") or "")[:10]


def _candidate_score(candidate: dict[str, Any], row: dict[str, Any]) -> int:
    score = 0
    row_race = row.get("race_number")
    if row_race is not None and candidate.get("race_number") == int(row_race):
        score += 4
    row_track = normalize_track(row.get("track"))
    candidate_track = normalize_track(candidate.get("track"))
    if row_track and candidate_track:
        if row_track == candidate_track:
            score += 3
        elif row_track in candidate_track or candidate_track in row_track:
            score += 1
    return score


def build_program_field_index(programs_dir: Path) -> dict[tuple[str, str, int], list[dict[str, Any]]]:
    index: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
    if not programs_dir.exists():
        return index

    for path in sorted(programs_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        race = payload.get("race") or {}
        race_date = _date(payload)
        race_number = _race_number(payload)
        track = race.get("track")
        if not race_date or race_number is None or not track:
            continue
        status = payload.get("program_table_mapping_status")
        if status not in {"mapped", "core_mapped"}:
            continue

        for horse in payload.get("horses") or []:
            try:
                number = int(horse.get("number"))
            except (TypeError, ValueError):
                continue
            name_key = normalize_person_or_horse(horse.get("horse"))
            if not name_key:
                continue
            candidate = {
                "race_number": race_number,
                "track": track,
                "horse_number": number,
                "horse_name": horse.get("horse"),
                "trainer": horse.get("trainer"),
                "driver": horse.get("driver") or horse.get("jockey"),
                "jockey": horse.get("jockey") or horse.get("driver"),
                "sex": horse.get("sex"),
                "age": horse.get("age"),
                "weight": horse.get("weight"),
                "draw": horse.get("draw"),
                "performance": horse.get("performance"),
                "gains": horse.get("gains"),
                "listed_chrono": horse.get("listed_chrono"),
                "listed_distance": horse.get("listed_distance"),
            }
            index.setdefault((race_date, name_key, number), []).append(candidate)
    return index


def merge_program_fields(
    rows: list[dict[str, Any]],
    index: dict[tuple[str, str, int], list[dict[str, Any]]],
) -> tuple[int, int]:
    matched = 0
    ambiguous = 0

    for row in rows:
        try:
            number = int(row.get("horse_number"))
        except (TypeError, ValueError):
            continue
        name_key = normalize_person_or_horse(row.get("horse_name"))
        date_key = str(row.get("date") or "")[:10]
        candidates = index.get((date_key, name_key, number), [])
        if not candidates:
            continue

        if len(candidates) == 1:
            candidate = candidates[0]
        else:
            scored = sorted(
                ((_candidate_score(candidate, row), candidate) for candidate in candidates),
                key=lambda item: -item[0],
            )
            if len(scored) == 1 or scored[0][0] > scored[1][0]:
                candidate = scored[0][1]
            else:
                ambiguous += 1
                continue

        for field_name in (
            "trainer",
            "driver",
            "jockey",
            "sex",
            "age",
            "weight",
            "draw",
            "performance",
            "gains",
            "listed_chrono",
            "listed_distance",
        ):
            value = candidate.get(field_name)
            # Keep the source dataset's participant record as primary evidence;
            # use program extraction only to fill gaps, never to overwrite it.
            if value not in (None, "") and row.get(field_name) in (None, ""):
                row[field_name] = value
        matched += 1

    return matched, ambiguous
