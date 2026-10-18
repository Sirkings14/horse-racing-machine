from __future__ import annotations

import ast
import json
import math
from pathlib import Path
from typing import Any

from datasets import load_dataset
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from src.model.historical_profile import build_walk_forward_profiles
from src.learning.result_truth import canonical_key
from src.dataset.build_dataset import labels_from_partial_arrival
OUT = BASE / "data" / "dataset" / "training_dataset_clean.json"
ROSTER_OUT = BASE / "data" / "rosters" / "historical_rosters.json"
PROGRAMS_DIR = BASE / "data" / "structured" / "programs"
SOURCE = "annaelmoussa/horse-racing-france"

def _pick(d: dict[str, Any], names: list[str], default=None):
    lower = {str(k).lower(): k for k in d}
    for n in names:
        k = lower.get(n.lower())
        if k is not None and d.get(k) not in (None, ""):
            return d[k]
    return default

def _num(v):
    try:
        x = float(str(v).replace(",", "."))
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None

def _key(v):
    return str(v or "").strip()

def _participant_key(p: dict[str, Any]) -> str:
    direct = _key(_pick(p, ["raceKey", "race_key"]))
    if direct:
        return direct
    date = str(_pick(p, ["date", "date_course"], "") or "")[:10]
    reunion = _num(_pick(p, ["numReunion", "reunion_number"]))
    course = _num(_pick(p, ["numCourse", "race_number", "course_number"]))
    if date and reunion is not None and course is not None:
        return f"{date}_R{int(reunion)}_C{int(course)}"
    return ""

def _validated_historical_rosters(candidates: dict[str, dict[str, dict[str, Any]]]) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    """Keep only historical participant rosters that match declared field size.

    This helper deliberately does not read or store arrival/finish targets.
    Incomplete rosters are omitted; conflicting complete rosters are marked so
    the result-truth validator can fail closed.
    """
    races: dict[str, dict[str, Any]] = {}
    runner_count_mismatches = 0
    conflicting_complete_rosters = 0

    for race_key, source_groups in sorted(candidates.items()):
        complete: list[tuple[str, int, set[int]]] = []
        for source_key, source_record in sorted(source_groups.items()):
            try:
                expected = int(source_record.get("expected_count") or 0)
            except (TypeError, ValueError):
                expected = 0
            numbers: set[int] = set()
            for value in source_record.get("horse_numbers") or []:
                try:
                    number = int(value)
                except (TypeError, ValueError):
                    continue
                if number > 0:
                    numbers.add(number)
            if expected <= 0 or len(numbers) != expected:
                runner_count_mismatches += 1
                continue
            complete.append((source_key, expected, numbers))

        if not complete:
            continue

        signatures = {
            (expected, tuple(sorted(numbers)))
            for _, expected, numbers in complete
        }
        if len(signatures) > 1:
            races[race_key] = {
                "horse_numbers": [],
                "runners_count": 0,
                "conflict": True,
                "conflicting_source_meta_keys": sorted(source_key for source_key, _, _ in complete),
            }
            conflicting_complete_rosters += 1
            continue

        source_keys = sorted(source_key for source_key, _, _ in complete)
        _, expected, numbers = complete[0]
        races[race_key] = {
            "horse_numbers": sorted(numbers),
            "runners_count": expected,
            "conflict": False,
            "source_meta_keys": source_keys,
        }

    return races, {
        "candidate_races": len(candidates),
        "validated_rosters": sum(not item.get("conflict", False) for item in races.values()),
        "conflicting_complete_rosters": conflicting_complete_rosters,
        "runner_count_mismatches": runner_count_mismatches,
    }


def _arrival(v):
    if v is None:
        return []
    if isinstance(v, str):
        s = v.strip()
        try:
            v = json.loads(s)
        except Exception:
            try:
                v = ast.literal_eval(s)
            except Exception:
                return []
    if not isinstance(v, list):
        return []
    out = []
    for item in v:
        vals = item if isinstance(item, list) else [item]
        for x in vals:
            try:
                number = int(x)
            except (TypeError, ValueError, OverflowError):
                return []
            if number <= 0:
                return []
            out.append(number)
    return out


def _structured_personnel_index() -> tuple[dict[tuple[str, int], dict[str, str]], int]:
    """Index explicit jockey/trainer fields; exclude conflicting duplicate identities."""
    candidates: dict[tuple[str, int], set[tuple[str, str]]] = {}
    if not PROGRAMS_DIR.exists():
        return {}, 0
    for path in sorted(PROGRAMS_DIR.glob("*.json")):
        try:
            program = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(program, dict):
            continue
        race = program.get("race") if isinstance(program.get("race"), dict) else {}
        date_text = str(program.get("date") or "")[:10]
        track = str(race.get("track") or "").strip().upper()
        try:
            race_number = int(race.get("race_number"))
        except (TypeError, ValueError):
            continue
        if not date_text or not track or race_number <= 0:
            continue
        for horse in program.get("horses") or []:
            if not isinstance(horse, dict):
                continue
            try:
                number = int(horse.get("number"))
            except (TypeError, ValueError):
                continue
            if number <= 0:
                continue
            jockey = str(next((horse.get(k) for k in ("jockey", "driver", "jockey_name", "driver_name", "jockeyName", "driverName") if horse.get(k) not in (None, "")), "") or "").strip()
            trainer = str(next((horse.get(k) for k in ("trainer", "entraineur", "trainer_name", "trainerName") if horse.get(k) not in (None, "")), "") or "").strip()
            candidates.setdefault((f"{date_text}|{track}|{race_number}", number), set()).add((jockey, trainer))
    index: dict[tuple[str, int], dict[str, str]] = {}
    conflicts = 0
    for key, identities in candidates.items():
        nonempty = {pair for pair in identities if pair != ("", "")}
        if len(nonempty) > 1:
            conflicts += 1
            continue
        if nonempty:
            jockey, trainer = next(iter(nonempty))
            index[key] = {"jockey": jockey, "trainer": trainer}
    return index, conflicts

def main():
    personnel_index, personnel_conflicts = _structured_personnel_index()
    print(json.dumps({"structured_personnel_index_rows": len(personnel_index), "conflicting_personnel_identities_excluded": personnel_conflicts}, indent=2))
    print("Loading race metadata...")
    courses = load_dataset(SOURCE, "courses", split="train", streaming=True)
    race_meta = {}
    for i, r in enumerate(courses):
        key = _key(_pick(r, ["raceKey", "race_key"]))
        if not key:
            date = str(_pick(r, ["date", "date_course"], "") or "")[:10]
            reunion = _num(_pick(r, ["numReunion", "reunion_number"]))
            course = _num(_pick(r, ["numCourse", "race_number", "course_number"]))
            if date and reunion is not None and course is not None:
                key = f"{date}_R{int(reunion)}_C{int(course)}"
        if not key:
            continue
        arr = _arrival(_pick(r, ["ordreArrivee", "ordre_arrivee", "finish_order"]))
        race_meta[key] = {
            "date": str(_pick(r, ["date", "date_course"], "") or "")[:10],
            "track": str(_pick(r, ["hippodrome", "track"], "") or ""),
            "race_number": int(_num(_pick(r, ["numCourse", "race_number"], 0)) or 0),
            "distance": int(_num(_pick(r, ["distance"], 0)) or 0),
            "runners_count": int(_num(_pick(r, ["nombreDeclaresPartants", "runners_count"], 0)) or 0),
            "prize_euros": _num(_pick(r, ["montantPrix", "prize_euros", "allocation_eur"])),
            "race_type": str(_pick(r, ["specialite", "discipline", "race_type"], "") or ""),
            "arrival": arr,
        }
        if i and i % 25000 == 0:
            print("courses:", i)

    print("Race metadata:", len(race_meta))
    participants = load_dataset(SOURCE, "participants", split="train", streaming=True)
    rows, columns_seen = [], set()
    matched_meta = matched_arrival = matched_number = 0
    roster_candidates: dict[str, dict[str, dict[str, Any]]] = {}
    participant_numbers_by_key: dict[str, set[int]] = {}
    participant_number_occurrences_by_key: dict[str, list[int]] = {}

    for i, p in enumerate(participants):
        columns_seen.update(p.keys())
        key = _participant_key(p)
        meta = race_meta.get(key)
        if meta:
            matched_meta += 1

        raw_horse_number = _num(_pick(p, ["numero", "num", "numeroPmu", "numPmu", "horse_number", "program_number"]))
        horse_number = (
            int(raw_horse_number)
            if raw_horse_number is not None and raw_horse_number > 0 and raw_horse_number.is_integer()
            else None
        )

        if meta and horse_number is not None:
            participant_numbers_by_key.setdefault(key, set()).add(horse_number)
            participant_number_occurrences_by_key.setdefault(key, []).append(horse_number)

        # Build roster candidates from all participants before consulting arrival.
        # This is an independent roster source, not a result-derived finisher list.
        if (
            meta and meta.get("date") and meta.get("track")
            and int(meta.get("race_number") or 0) > 0 and horse_number is not None
        ):
            roster_key = canonical_key(meta["date"], meta["track"], meta["race_number"])
            if roster_key:
                sources = roster_candidates.setdefault(roster_key, {})
                source = sources.setdefault(key, {
                    "expected_count": int(meta.get("runners_count") or 0),
                    "horse_numbers": set(),
                })
                source["horse_numbers"].add(horse_number)

        if not meta or not meta["date"] or not meta["arrival"]:
            continue
        matched_arrival += 1
        if horse_number is None:
            continue
        pos = meta["arrival"].index(horse_number) + 1 if horse_number in meta["arrival"] else None
        if pos is not None:
            matched_number += 1
        target_labels = labels_from_partial_arrival(pos, len(meta["arrival"]))
        horse_name = str(_pick(p, ["cheval", "nomCheval", "horse", "horse_name", "nom"], f"HORSE_{horse_number}") or f"HORSE_{horse_number}").strip()
        horse_id = _pick(p, ["horse_id", "horseId", "horse_uid", "horseUid", "idCheval", "id_cheval", "identifiantCheval", "identifiant_cheval"])
        personnel_key = (f"{meta['date']}|{str(meta['track']).strip().upper()}|{int(meta['race_number'])}", horse_number)
        personnel = personnel_index.get(personnel_key, {})
        rows.append({
            "race_key": key, "date": meta["date"], "track": meta["track"],
            "race_number": meta["race_number"], "distance": meta["distance"],
            "runners_count": meta["runners_count"], "prize_euros": meta["prize_euros"],
            "race_type": meta["race_type"], "horse_number": horse_number,
            "horse_name": horse_name, "horse_id": horse_id,
            "jockey": personnel.get("jockey") or None, "trainer": personnel.get("trainer") or None,
            "finish_position": pos,
            "won": target_labels["won"], "top3": target_labels["top3"],
            "top4": target_labels["top4"], "top5": target_labels["top5"],
            "arrival_positions_available": target_labels["arrival_positions_available"],
            "target_won_known": target_labels["target_won_known"],
            "target_top3_known": target_labels["target_top3_known"],
            "target_top4_known": target_labels["target_top4_known"],
            "target_top5_known": target_labels["target_top5_known"],
            "weight": _num(_pick(p, ["poids", "weight", "carried_weight", "poidsporte"])),
            "draw": _num(_pick(p, ["corde", "draw", "stall", "numCorde", "placeCorde"])),
            "win_odds_decimal": _num(_pick(p, [
                "cotePMU", "cotePmu", "cote_pmu", "odds", "odds_decimal",
                "coteGagnant", "starting_price", "starting_price_decimal"
            ])),
        })
        if i and i % 100000 == 0:
            print("participants:", i, "meta_matches:", matched_meta, "arrival_matches:", matched_arrival, "usable:", len(rows))

    # Fail closed for races whose result duplicates a runner or names a runner
    # absent from the complete participant roster. Short but internally valid
    # arrivals are retained with unknown labels masked per cutoff.
    invalid_arrival_races = set()
    for race_key, meta in race_meta.items():
        arrival = meta.get("arrival") or []
        if not arrival:
            continue
        roster_numbers = participant_numbers_by_key.get(race_key, set())
        occurrences = participant_number_occurrences_by_key.get(race_key, [])
        if (
            len(arrival) != len(set(arrival))
            or not set(arrival).issubset(roster_numbers)
            or len(occurrences) != len(set(occurrences))
        ):
            invalid_arrival_races.add(race_key)
    if invalid_arrival_races:
        before = len(rows)
        rows = [row for row in rows if row["race_key"] not in invalid_arrival_races]
        print(json.dumps({
            "invalid_arrival_races_rejected": len(invalid_arrival_races),
            "rows_removed_for_ambiguous_arrivals": before - len(rows),
        }, indent=2))

    print(json.dumps({
        "participant_columns": sorted(columns_seen),
        "meta_matches": matched_meta,
        "arrival_matches": matched_arrival,
        "number_matches": matched_number,
    }, indent=2))

    if not rows:
        raise RuntimeError("No rows built after participant/race join")

    historical_rosters, roster_stats = _validated_historical_rosters(roster_candidates)
    ROSTER_OUT.parent.mkdir(parents=True, exist_ok=True)
    ROSTER_OUT.write_text(json.dumps({
        "schema_version": 1,
        "source": SOURCE,
        "roster_semantics": "participant numbers joined to race metadata before arrival-target filtering",
        "target_fields_included": False,
        "races": historical_rosters,
        "coverage": roster_stats,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({"historical_roster_index": str(ROSTER_OUT.relative_to(BASE)), **roster_stats}, indent=2))

    rows.sort(key=lambda x: (x["date"], x["race_key"], x["horse_number"]))
    rows = build_walk_forward_profiles(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    odds = sum(r.get("win_odds_decimal") is not None for r in rows)
    print(json.dumps({
        "rows": len(rows), "races": len({r["race_key"] for r in rows}),
        "first_date": rows[0]["date"], "last_date": rows[-1]["date"],
        "explicit_win_odds_rows": odds, "explicit_win_odds_rate": round(odds / len(rows), 4),
        "horse_identity_source": ("stable_id" if any(r.get("horse_id") not in (None, "") for r in rows) else "normalized_name"),
    }, indent=2))

if __name__ == "__main__":
    main()
