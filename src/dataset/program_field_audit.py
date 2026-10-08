from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[2]
PROGRAMS_DIR = BASE_DIR / "data" / "structured" / "programs"
PROCESSED_DIR = BASE_DIR / "data" / "processed" / "programs"

FRACTIONAL_RE = re.compile(r"\b\d+(?:[.,]\d+)?/\d+(?:[.,]\d+)?\b")
SEX_AGE_RE = re.compile(r"\b[HFM]\.?\s*\d{1,2}\b", re.IGNORECASE)
PERF_RE = re.compile(r"\b(?:[0-9DAA]{1,2})(?:\.[0-9DAA]{1,2}){2,5}\b", re.IGNORECASE)
WEIGHT_RE = re.compile(r"\b(?:POIDS|WEIGHT|KG|KGS)\b", re.IGNORECASE)
DRAW_RE = re.compile(r"\b(?:CORDE|STA(?:LLE)?|DRAW|STALLE)\b", re.IGNORECASE)
DRIVER_RE = re.compile(r"\b(?:DRIVERS?|JOCKEYS?)\b", re.IGNORECASE)
TRAINER_RE = re.compile(r"\b(?:ENTRAINEURS?|TRAINERS?)\b", re.IGNORECASE)
OWNER_RE = re.compile(r"\b(?:PROPRIETAIRES?|PROPRIÉTAIRES?|OWNERS?)\b", re.IGNORECASE)


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _source_text(program: dict[str, Any]) -> str:
    source = str(program.get("source_file") or "")
    if source:
        path = PROCESSED_DIR / source.replace(".pdf", ".txt")
        if path.exists():
            try:
                return path.read_text(encoding="utf-8")
            except OSError:
                pass
    return ""


def _counts(text: str, expected: int) -> dict[str, Any]:
    fractions = FRACTIONAL_RE.findall(text)
    sex_age = SEX_AGE_RE.findall(text)
    perf = PERF_RE.findall(text)
    return {
        "sex_age_exact": len(sex_age) == expected,
        "sex_age_tokens": len(sex_age),
        "performance_exact_or_more": len(perf) >= expected,
        "performance_tokens": len(perf),
        "fractional_odds_tokens": len(fractions),
        "weight_marker": bool(WEIGHT_RE.search(text)),
        "draw_marker": bool(DRAW_RE.search(text)),
        "driver_marker": bool(DRIVER_RE.search(text)),
        "trainer_marker": bool(TRAINER_RE.search(text)),
        "owner_marker": bool(OWNER_RE.search(text)),
    }


def audit() -> dict[str, Any]:
    files = sorted(PROGRAMS_DIR.glob("*.json"))
    reports: list[dict[str, Any]] = []
    structured_key_counts: Counter[str] = Counter()

    for path in files:
        program = _load_json(path)
        if not program:
            continue
        race = program.get("race") or {}
        expected = int(race.get("runners_count") or 0)
        horses = program.get("horses") or []
        for horse in horses:
            if isinstance(horse, dict):
                structured_key_counts.update(k for k, v in horse.items() if v not in (None, "", []))

        text = _source_text(program)
        raw = _counts(text, expected)
        reports.append({
            "file": path.name,
            "date": program.get("date"),
            "track": race.get("track"),
            "race_type": race.get("race_type"),
            "runners": expected,
            "horses": len(horses),
            "program_table_mapping_status": program.get("program_table_mapping_status", "unmapped"),
            "horse_description_nonempty": sum(
                bool(isinstance(h, dict) and str(h.get("description") or "").strip())
                for h in horses
            ),
            **raw,
        })

    n = len(reports)

    def race_rate(key: str) -> float:
        return round(sum(bool(r.get(key)) for r in reports) / n, 4) if n else 0.0

    def runner_rate(numerator_key: str) -> float:
        denom = sum(int(r.get("runners") or 0) for r in reports)
        if not denom:
            return 0.0
        return round(sum(int(r.get(numerator_key) or 0) for r in reports) / denom, 4)

    summary = {
        "program_files": n,
        "structured_nonempty_keys": dict(structured_key_counts),
        "race_level_coverage": {
            "program_table_mapped": round(
                sum(r.get("program_table_mapping_status") == "mapped" for r in reports) / n, 4
            ) if n else 0.0,
            "sex_age_exact": race_rate("sex_age_exact"),
            "performance_exact_or_more": race_rate("performance_exact_or_more"),
            "weight_marker": race_rate("weight_marker"),
            "draw_marker": race_rate("draw_marker"),
            "driver_marker": race_rate("driver_marker"),
            "trainer_marker": race_rate("trainer_marker"),
            "owner_marker": race_rate("owner_marker"),
        },
        "runner_level_description_coverage": runner_rate("horse_description_nonempty"),
        "notes": [
            "This is an audit only: it does not add fields to model training or production.",
            "Raw token counts are evidence of source availability, not proof of correct runner-to-value alignment.",
            "A field must pass an exact runner-level mapping test before it can be promoted into V3/V4 features.",
        ],
        "programs": reports,
    }
    return summary


if __name__ == "__main__":
    print(json.dumps(audit(), ensure_ascii=False, indent=2))
