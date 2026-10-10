from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from src.model.race_type import canonical_race_type, race_type_family

OUTPUT = BASE / "data" / "evaluation" / "race_type_coverage.json"
FIELD_NAMES = (
    "performance", "gains", "listed_chrono", "listed_distance",
    "sex", "age", "weight", "draw", "trainer", "jockey", "driver",
)


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _add_program(payload: dict[str, Any], source: str, types: Counter, races: set,
                 runners: Counter, fields: dict[tuple[str, str], Counter]) -> None:
    race = payload.get("race") or {}
    label = canonical_race_type(race.get("race_type")) or "UNKNOWN"
    types[(source, label, race_type_family(label))] += 1
    date = str(payload.get("date") or "")[:10]
    track = str(race.get("track") or "").strip().upper()
    number = race.get("race_number")
    races.add((source, date, track, str(number)))
    for horse in payload.get("horses") or []:
        if not isinstance(horse, dict):
            continue
        runners[(source, label)] += 1
        for field in FIELD_NAMES:
            if horse.get(field) not in (None, ""):
                fields[(source, label)][field] += 1


def main() -> dict[str, Any]:
    type_counts: Counter = Counter()
    race_keys: set = set()
    runner_counts: Counter = Counter()
    field_counts: dict[str, Counter] = defaultdict(Counter)

    sources = (
        ("historical_program", BASE / "data" / "structured" / "programs"),
        ("live_program", BASE / "data" / "live" / "structured"),
    )
    program_files = 0
    for source, folder in sources:
        if not folder.exists():
            continue
        for path in sorted(folder.glob("*.json")):
            payload = _read(path)
            if not isinstance(payload, dict) or not isinstance(payload.get("race"), dict):
                continue
            program_files += 1
            _add_program(payload, source, type_counts, race_keys, runner_counts, field_counts)

    report = {
        "schema_version": 1,
        "program_files_audited": program_files,
        "unique_source_races": len(race_keys),
        "race_types": [
            {"source": source, "race_type": label, "family": family, "races": count}
            for (source, label, family), count in sorted(type_counts.items())
        ],
        "runner_counts_by_type": [
            {"source": source, "race_type": label, "runners": count}
            for (source, label), count in sorted(runner_counts.items())
        ],
        "pre_race_field_coverage": [
            {
                "source": source,
                "race_type": label,
                "runners": runner_counts[(source, label)],
                "fields": {
                    field: {
                        "present": field_counts[(source, label)][field],
                        "coverage": round(
                            field_counts[(source, label)][field] /
                            max(runner_counts[(source, label)], 1), 4
                        ),
                    }
                    for field in FIELD_NAMES
                },
            }
            for source, label in sorted(runner_counts)
        ],
        "policy": {
            "press_estimates_are_not_market_odds": True,
            "missing_fields_are_not_imputed": True,
            "this_audit_does_not_promote_models": True,
        },
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "program_files_audited": report["program_files_audited"],
        "unique_source_races": report["unique_source_races"],
        "race_types": report["race_types"],
        "pre_race_field_coverage": report["pre_race_field_coverage"],
        "output": str(OUTPUT.relative_to(BASE)),
    }, indent=2, ensure_ascii=False))
    return report


if __name__ == "__main__":
    main()
