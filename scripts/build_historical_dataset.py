from __future__ import annotations

import ast
import json
import math
from pathlib import Path
from typing import Any

from datasets import load_dataset
from src.model.historical_profile import build_walk_forward_profiles

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / "data" / "dataset" / "training_dataset_clean.json"
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
                out.append(int(x))
            except Exception:
                pass
    return out

def main():
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
    for i, p in enumerate(participants):
        columns_seen.update(p.keys())
        key = _participant_key(p)
        meta = race_meta.get(key)
        if meta:
            matched_meta += 1
        if not meta or not meta["date"] or not meta["arrival"]:
            continue
        matched_arrival += 1
        horse_number = _num(_pick(p, ["numero", "num", "numeroPmu", "numPmu", "horse_number", "program_number"]))
        if horse_number is None:
            continue
        horse_number = int(horse_number)
        try:
            pos = meta["arrival"].index(horse_number) + 1
        except ValueError:
            continue
        matched_number += 1
        horse_name = str(_pick(p, ["cheval", "nomCheval", "horse", "horse_name", "nom"], f"HORSE_{horse_number}") or f"HORSE_{horse_number}").strip()
        rows.append({
            "race_key": key, "date": meta["date"], "track": meta["track"],
            "race_number": meta["race_number"], "distance": meta["distance"],
            "runners_count": meta["runners_count"], "prize_euros": meta["prize_euros"],
            "race_type": meta["race_type"], "horse_number": horse_number,
            "horse_name": horse_name, "finish_position": pos, "won": int(pos == 1),
            "top3": int(pos <= 3), "top5": int(pos <= 5),
            "weight": _num(_pick(p, ["poids", "weight", "carried_weight", "poidsporte"])),
            "draw": _num(_pick(p, ["corde", "draw", "stall", "numCorde", "placeCorde"])),
            "win_odds_decimal": _num(_pick(p, [
                "cotePMU", "cotePmu", "cote_pmu", "odds", "odds_decimal",
                "coteGagnant", "starting_price", "starting_price_decimal"
            ])),
        })
        if i and i % 100000 == 0:
            print("participants:", i, "meta_matches:", matched_meta, "arrival_matches:", matched_arrival, "usable:", len(rows))

    print(json.dumps({
        "participant_columns": sorted(columns_seen),
        "meta_matches": matched_meta,
        "arrival_matches": matched_arrival,
        "number_matches": matched_number,
    }, indent=2))

    if not rows:
        raise RuntimeError("No rows built after participant/race join")
    rows.sort(key=lambda x: (x["date"], x["race_key"], x["horse_number"]))
    rows = build_walk_forward_profiles(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    odds = sum(r.get("win_odds_decimal") is not None for r in rows)
    print(json.dumps({
        "rows": len(rows), "races": len({r["race_key"] for r in rows}),
        "first_date": rows[0]["date"], "last_date": rows[-1]["date"],
        "explicit_win_odds_rows": odds, "explicit_win_odds_rate": round(odds / len(rows), 4),
    }, indent=2))

if __name__ == "__main__":
    main()
