from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from src.model.logistic_model import LogisticModel

BASE_DIR = Path(__file__).resolve().parents[2]
PROGRAM_DIR = BASE_DIR / "data" / "structured" / "programs"
DATASET_FILE = BASE_DIR / "data" / "dataset" / "training_dataset_clean.json"
MODEL_DIR = BASE_DIR / "data" / "model"
OUTPUT_FILE = MODEL_DIR / "latest_prediction.json"

def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))

def race_key(program):
    race = program.get("race") or {}
    date = program.get("date")
    track = race.get("track") or program.get("track")
    number = race.get("race_number")
    if not date or not track or number is None:
        return None
    return f"{str(date).strip()}|{str(track).strip().upper()}|{int(number)}"

def program_to_rows(program):
    race = program.get("race") or {}
    rankings = program.get("rankings") or {}
    positions = {}
    for name in ("favorites","form","class","progress","regularity"):
        positions[name] = {}
        for i, value in enumerate(rankings.get(name) or [], 1):
            try: positions[name][int(value)] = i
            except (TypeError, ValueError): pass
    rows = []
    for horse in program.get("horses") or []:
        try: number = int(horse.get("number"))
        except (TypeError, ValueError): continue
        if number <= 0: continue
        ranks = {f"{name}_rank": positions[name].get(number) for name in positions}
        rank_values = [v for v in ranks.values() if v is not None]
        rows.append({"race_key":race_key(program),"date":program.get("date"),"track":race.get("track"),
            "race_number":race.get("race_number"),"race_name":race.get("race_name"),
            "race_type":race.get("race_type"),"distance":race.get("distance"),
            "runners_count":race.get("runners_count"),"horse_number":number,
            "horse_name":horse.get("horse"),"horse_description":horse.get("description"),
            **ranks,"ranking_average":sum(rank_values)/len(rank_values) if rank_values else None,
            "ranking_presence":len(rank_values)})
    return rows

def main():
    historical = {str(r.get("race_key")) for r in load_json(DATASET_FILE)}
    models = {d: LogisticModel.from_dict(load_json(MODEL_DIR / f"top{d}_model.json")) for d in (3,4,5)}
    programs = []
    for path in PROGRAM_DIR.glob("*.json"):
        try: payload = load_json(path)
        except Exception: continue
        if isinstance(payload, dict) and payload.get("race") and payload.get("horses"):
            programs.append((path,payload))
    programs.sort(key=lambda x: str(x[1].get("date") or ""), reverse=True)
    selected = next((x for x in programs if race_key(x[1]) not in historical), None)
    mode = "future_or_unmatched"
    if selected is None:
        if not programs: raise ValueError("No structured program files are available for prediction.")
        selected = programs[0]
        mode = "retrospective_latest_available"
    path, program = selected
    rows = program_to_rows(program)
    probabilities = {d: models[d].predict_proba(rows) for d in (3,4,5)}
    ranked = []
    for i, row in enumerate(rows):
        p3,p4,p5 = (float(probabilities[d][i]) for d in (3,4,5))
        score = 0.5*p3 + 0.3*p4 + 0.2*p5
        ranked.append({"horse_number":int(row["horse_number"]),"horse_name":row.get("horse_name"),
            "probability_top3":round(p3,6),"probability_top4":round(p4,6),
            "probability_top5":round(p5,6),"ensemble_score":round(score,6)})
    ranked.sort(key=lambda x:(-x["ensemble_score"],x["horse_number"]))
    for i, item in enumerate(ranked,1): item["predicted_rank"] = i
    adaptive = 5
    if len(ranked) >= 5:
        if ranked[2]["probability_top3"] - ranked[3]["probability_top3"] >= 0.12:
            adaptive = 3
        elif ranked[3]["probability_top4"] - ranked[4]["probability_top4"] >= 0.10:
            adaptive = 4
    result = {"generated_at":datetime.utcnow().isoformat()+"Z","mode":mode,"source_program":path.name,
        "race_key":race_key(program),"race":program.get("race"),
        "recommended_numbers":[x["horse_number"] for x in ranked[:adaptive]],
        "adaptive_top_count":adaptive,"top3_numbers":[x["horse_number"] for x in ranked[:3]],
        "ranked_horses":ranked}
    OUTPUT_FILE.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding="utf-8")
    print(f"Race: {result['race_key']}")
    print(f"Adaptive recommendation ({adaptive}): {result['recommended_numbers']}")

if __name__ == "__main__":
    main()
