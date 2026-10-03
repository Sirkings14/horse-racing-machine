from __future__ import annotations
import json, re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
import numpy as np
from src.live.registry import eligible_races, LIVE_DIR
from src.model.historical_profile import build_walk_forward_profiles
from src.model.truth_gate import validate_program
from src.model.v3_model import V3LogisticModel
from src.model.autopilot_guard import build_autopilot_guard

BASE_DIR=Path(__file__).resolve().parents[2]
DATASET_FILE=BASE_DIR/"data/dataset/training_dataset_clean.json"
MODEL_FILE=BASE_DIR/"data/model/v3_models.json"
OUTPUT_FILE=BASE_DIR/"data/model/latest_v3_prediction.json"
PREDICTIONS_DIR=BASE_DIR/"data/predictions"

def _json(path): return json.loads(path.read_text(encoding="utf-8"))

def _meta(program):
    race=program.get("race") or {}
    return {"date":program.get("date"),"track":race.get("track"),"race_number":race.get("race_number"),"race_name":race.get("race_name"),"race_type":race.get("race_type"),"distance":race.get("distance"),"runners_count":race.get("runners_count")}

def _key(program):
    m=_meta(program)
    if not m["date"] or not m["track"] or m["race_number"] is None: return None
    return f'{m["date"]}|{str(m["track"]).strip().upper()}|{int(m["race_number"])}'

def _live_rows(program):
    m=_meta(program); key=_key(program); rows=[]
    for horse in program.get("horses") or []:
        try: number=int(horse.get("number"))
        except (TypeError,ValueError): continue
        rows.append({"race_key":key,"date":m["date"],"track":m["track"],"race_number":m["race_number"],"race_name":m["race_name"],"race_type":m["race_type"],"distance":m["distance"],"runners_count":m["runners_count"],"horse_number":number,"horse_name":horse.get("horse")})
    return rows

def _save(result):
    OUTPUT_FILE.parent.mkdir(parents=True,exist_ok=True); PREDICTIONS_DIR.mkdir(parents=True,exist_ok=True)
    raw=json.dumps(result,indent=2,ensure_ascii=False); OUTPUT_FILE.write_text(raw,encoding="utf-8")
    if result.get("race_key"):
        safe=re.sub(r"[^A-Za-z0-9_.-]+","_",result["race_key"])
        (PREDICTIONS_DIR/f"{safe}_v3.json").write_text(raw,encoding="utf-8")

def no_prediction(reason,**extra):
    result={"prediction_id":f"{key}|{datetime.now(timezone.utc).isoformat()}","generated_at":datetime.now(timezone.utc).isoformat(),"model_version":bundle.get("model_version"),"mode":"v3_evidence_no_press","race_key":key,"race":_meta(program),"truth_gate":gate,"press_dependency":False,"post_race_feature_policy":"hard_exclusion","confidence":confidence,"model_agreement":"high" if disagreement<0.06 else "medium" if disagreement<0.10 else "low","recommended_numbers":[x["horse_number"] for x in ranked[:5]],"final_five":[x["horse_number"] for x in ranked[:5]],"ranked_horses":ranked,"selection_policy":"independent_evidence_ensemble_with_disagreement_penalty"}
    guard=build_autopilot_guard({"ranked_horses":ranked,"monitoring":{"agreement":result["model_agreement"]},"difficulty":{}})
    result["autopilot_guard"]=guard
    if guard.get("decision")=="PASS":
        result["live_decision"]="NO_BET"
        result["no_bet_reason"]=guard.get("gate_reasons") or ["autopilot_guard_blocked_live_play"]
        result["recommended_numbers"]=[]
        result["final_five"]=[]
    else:
        result["live_decision"]="PLAY_CANDIDATE"
    _save(result)
    print("V3 FINAL 5:",result["final_five"])
    return result

if __name__=="__main__": main()
