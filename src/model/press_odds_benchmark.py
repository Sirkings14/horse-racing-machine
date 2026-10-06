from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.model.historical_profile import build_walk_forward_profiles
from src.model.v3_model import V3LogisticModel
from src.parsers.program_parser import parse_program_file

BASE = Path(__file__).resolve().parents[2]
HISTORY_FILE = BASE / "data/dataset/training_dataset_clean.json"
MODEL_FILE = BASE / "data/model/v3_models.json"
MATCHED_FILE = BASE / "data/matched/matched_races.json"
PROGRAM_DIR = BASE / "data/processed/programs"
OUTPUT_FILE = BASE / "data/model/press_odds_benchmark_report.json"
EDGE = 0.08
SOURCES = {"paris_turf": "Paris Turf", "tierce_magazine": "Tierce Magazine"}


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def odds(value):
    try:
        x = float(value)
        return x if x > 1 else None
    except (TypeError, ValueError):
        return None


def prob(value):
    try:
        x = float(value)
        return x if 0 <= x <= 1 else None
    except (TypeError, ValueError):
        return None


def key(program):
    race = program.get("race") or {}
    try:
        number = int(race["race_number"])
    except (KeyError, TypeError, ValueError):
        return None
    date = program.get("date")
    track = str(race.get("track") or "").strip().upper()
    return f"{date}|{track}|{number}" if date and track else None


def rows_from_program(program):
    race = program["race"]
    k = key(program)
    return [{
        "race_key": k,
        "date": program.get("date"),
        "track": race.get("track"),
        "race_number": race.get("race_number"),
        "race_name": race.get("race_name"),
        "race_type": race.get("race_type"),
        "distance": race.get("distance"),
        "runners_count": race.get("runners_count"),
        "prize_euros": race.get("prize_euros"),
        "horse_number": int(h["number"]),
        "horse_name": h.get("horse"),
    } for h in program.get("horses", []) if str(h.get("number", "")).isdigit()]


def rank(models, rows):
    p1, p3, p5 = (models[name].predict_proba(rows) for name in ("winner", "top3", "top5"))
    out = []
    for row, a, b, c in zip(rows, p1, p3, p5):
        disagreement = (abs(float(a)-float(b)) + abs(float(b)-float(c))) / 2
        score = max(0.0, 0.25*float(a) + 0.50*float(b) + 0.25*float(c) - 0.15*disagreement)
        out.append({
            "horse_number": int(row["horse_number"]),
            "horse_name": row.get("horse_name"),
            "probability_winner": round(float(a), 6),
            "probability_top3": round(float(b), 6),
            "probability_top5": round(float(c), 6),
            "ensemble_score": round(score, 6),
        })
    return sorted(out, key=lambda x: (-x["ensemble_score"], -x["probability_top3"], x["horse_number"]))


def accounting(races, source, value_only=False):
    bets = wins = 0
    stake = returned = 0.0
    edges = []
    equity = peak = drawdown = 0.0
    chronological = []

    for race in races:
        selected = []
        race_stake = race_return = 0.0
        prices = (race["press_odds"].get(source) or {})
        for horse in race["top5"]:
            n = str(horse["horse_number"])
            o = odds((prices.get(n) or {}).get("decimal"))
            p = prob(horse.get("probability_winner"))
            if o is None or p is None:
                continue
            edge = p - 1.0/o
            if value_only and edge < EDGE:
                continue
            selected.append(horse["horse_number"])
            bets += 1
            wins += int(horse["horse_number"] == race["winner"])
            stake += 1.0
            race_stake += 1.0
            edges.append(edge)
            if horse["horse_number"] == race["winner"]:
                returned += o
                race_return += o
        equity += race_return - race_stake
        peak = max(peak, equity)
        drawdown = max(drawdown, peak-equity)
        chronological.append({"race_key": race["race_key"], "selected": selected, "profit": race_return-race_stake})

    profit = returned - stake
    return {
        "bets": bets,
        "wins": wins,
        "win_rate": round(wins/bets, 4) if bets else None,
        "total_stake": round(stake, 4),
        "total_return": round(returned, 4),
        "profit": round(profit, 4),
        "roi": round(profit/stake, 4) if stake else None,
        "average_probability_edge": round(sum(edges)/len(edges), 4) if edges else None,
        "maximum_drawdown_units": round(drawdown, 4),
        "chronological": chronological,
    }


def main():
    history = load(HISTORY_FILE)
    bundle = load(MODEL_FILE)
    matched = load(MATCHED_FILE)
    if bundle.get("production_approved") is not True:
        raise RuntimeError("V4 model bundle is not production-approved.")

    records = {}
    winners = {}
    for item in matched:
        if not isinstance(item, dict):
            continue
        if str((item.get("match") or {}).get("status") or "").upper() not in {"MATCHED","EXACT","VERIFIED","CONFIRMED"}:
            continue
        stored = item.get("program") or {}
        source_file = stored.get("source_file")
        if not source_file:
            continue
        path = PROGRAM_DIR / str(source_file)
        if not path.exists():
            continue
        program = parse_program_file(path)
        k = key(program)
        result = item.get("result") or {}
        arrival = result.get("arrival") or []
        winner = arrival[0] if arrival else result.get("winner")
        if k and program.get("press_odds") and winner is not None:
            records[k] = program
            winners[k] = int(winner)

    cutoff = max(str(r.get("date") or "")[:10] for r in history)
    all_programs = sorted(records.values(), key=lambda p: (str(p.get("date") or ""), key(p) or ""))
    programs = [p for p in all_programs if str(p.get("date") or "")[:10] > cutoff]
    current = [row for p in programs for row in rows_from_program(p)]
    profiled = build_walk_forward_profiles(history + current)
    by_key = {}
    for r in profiled:
        if r.get("race_key") in records:
            by_key.setdefault(r["race_key"], []).append(r)

    races = []
    models = {name: V3LogisticModel.from_dict(value) for name, value in (bundle.get("models") or {}).items()}
    for program in programs:
        k = key(program)
        profiled_rows = by_key.get(k, [])
        if len(profiled_rows) != len(program.get("horses", [])):
            continue
        ranked = rank(models, profiled_rows)
        press = program.get("press_odds") or {}
        complete = {
            source: all(
                odds(((press.get(source) or {}).get(str(h["horse_number"])) or {}).get("decimal")) is not None
                for h in ranked[:5]
            )
            for source in SOURCES
        }
        races.append({
            "race_key": k,
            "date": program.get("date"),
            "winner": winners[k],
            "press_odds": press,
            "complete_top5_prices": complete,
            "top5": ranked[:5],
        })

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "benchmark_available" if races else "no_benchmark_races",
        "method": "out_of_sample_v4_scoring_on_stored_lonab_programs_vs_published_press_prices",
        "training_history_end_date": cutoff,
        "programs_found_before_cutoff": len(all_programs) - len(programs),
        "benchmark_races": len(races),
        "market_evidence_gate_unlocked": False,
        "press_prices_are_market_evidence": False,
        "policy": {
            "press_publications_are_benchmark_only": True,
            "exact_prediction_time_price_timestamp_available": False,
            "operator_or_tote_prices_required_for_live_economic_validation": True,
            "never_invent_market_odds": True,
            "accepted_fractional_price_format": "N/1 only",
        },
        "sources": {},
        "races": races,
    }
    for source, label in SOURCES.items():
        priced = [r for r in races if r["complete_top5_prices"].get(source)]
        report["sources"][source] = {
            "label": label,
            "priced_races": len(priced),
            "priced_race_coverage": round(len(priced)/len(races), 4) if races else 0.0,
            "all_top5_accounting": accounting(priced, source),
            "value_filtered_accounting": accounting(priced, source, True),
        }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "benchmark_races": report["benchmark_races"],
        "sources": {
            source: {
                "priced_races": data["priced_races"],
                "priced_race_coverage": data["priced_race_coverage"],
                "top5_roi": data["all_top5_accounting"]["roi"],
                "value_filtered_bets": data["value_filtered_accounting"]["bets"],
                "value_filtered_roi": data["value_filtered_accounting"]["roi"],
            } for source, data in report["sources"].items()
        },
        "market_evidence_gate_unlocked": False,
    }, indent=2))
    if report["status"] != "benchmark_available" or not any(x["priced_races"] for x in report["sources"].values()):
        raise SystemExit("No usable published press-price benchmark found.")


if __name__ == "__main__":
    main()
