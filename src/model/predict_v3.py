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
from src.model.opportunity import score_race_opportunity

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
    race=program.get("race") or {}
    race_fields={"prize_euros":race.get("prize_euros")}
    for horse in program.get("horses") or []:
        try: number=int(horse.get("number"))
        except (TypeError,ValueError): continue
        # Preserve only fields supplied by the live program. This keeps the
        # prediction path schema-compatible with historical rows without
        # inventing horse attributes or importing post-race information.
        row={
            "race_key":key,"date":m["date"],"track":m["track"],
            "race_number":m["race_number"],"race_name":m["race_name"],
            "race_type":m["race_type"],"distance":m["distance"],
            "runners_count":m["runners_count"],**race_fields,
            "horse_number":number,"horse_name":horse.get("horse"),
        }
        for field_name in (
            "horse_id","horseId","horse_uid","horseUid","idCheval","id_cheval",
            "identifiantCheval","identifiant_cheval","weight","poids",
            "carried_weight","draw","stall","gate","box","jockey","driver",
            "trainer","entraineur","form_rank","recent_form_rank","forme_rank",
            "class_rank","classe_rank","favorite_rank","odds_rank","market_rank",
            "progress_rank","improvement_rank","regularity_rank","consistency_rank",
            "horse_description","description",
        ):
            if field_name in horse:
                row[field_name]=horse.get(field_name)
        rows.append(row)
    return rows

def _save(result):
    OUTPUT_FILE.parent.mkdir(parents=True,exist_ok=True); PREDICTIONS_DIR.mkdir(parents=True,exist_ok=True)
    raw=json.dumps(result,indent=2,ensure_ascii=False); OUTPUT_FILE.write_text(raw,encoding="utf-8")
    if result.get("race_key"):
        safe=re.sub(r"[^A-Za-z0-9_.-]+","_",result["race_key"])
        (PREDICTIONS_DIR/f"{safe}_v3.json").write_text(raw,encoding="utf-8")

def no_prediction(reason,**extra):
    result={"prediction_id":None,"generated_at":datetime.now(timezone.utc).isoformat(),"model_version":None,"mode":"v3_unavailable","reason":reason,"recommended_numbers":[],"ranked_horses":[],**extra}; _save(result); return result

def main():
    try:
        history=_json(DATASET_FILE)
        bundle=_json(MODEL_FILE)
        if not isinstance(history,list) or not history: return no_prediction("verified_training_dataset_unavailable")
        if bundle.get("press_dependency") is not False or bundle.get("post_race_feature_policy")!="hard_exclusion": return no_prediction("v3_artifact_policy_invalid")
        if bundle.get("production_approved") is not True: return no_prediction("v3_challenger_not_production_approved", promotion_gate=bundle.get("promotion_gate"))
        models={k:V3LogisticModel.from_dict(v) for k,v in (bundle.get("models") or {}).items()}
        if set(models)!= {"winner","top3","top5"}: return no_prediction("v3_model_bundle_incomplete")
    except Exception as error:
        return no_prediction(f"v3_artifact_unavailable: {error}")

    races=eligible_races(date.today().isoformat())
    if not races: return no_prediction("no_validated_current_or_future_race")
    entry=races[0]
    try: program=_json(LIVE_DIR/str(entry["structured_file"]))
    except Exception as error: return no_prediction(f"live_program_unreadable: {error}")
    gate=validate_program(program)
    if not gate["valid"]: return no_prediction("live_program_truth_gate_failed",truth_gate=gate)
    current=_live_rows(program); key=_key(program)
    if not key or len(current)!=int((_meta(program)["runners_count"] or 0)): return no_prediction("live_program_runner_data_incomplete",race_key=key,truth_gate=gate)

    profiled=build_walk_forward_profiles(history+current)
    current_profile=[r for r in profiled if r.get("race_key")==key]
    if len(current_profile)!=len(current): return no_prediction("current_profile_incomplete",race_key=key)

    p1=models["winner"].predict_proba(current_profile)
    p3=models["top3"].predict_proba(current_profile)
    p5=models["top5"].predict_proba(current_profile)
    ranked=[]
    for row,a,b,c in zip(current_profile,p1,p3,p5):
        completeness=float(row.get("data_completeness") or 0.0) 
        raw_score=0.25*float(a)+0.50*float(b)+0.25*float(c)
        disagreement=float(np.std([a,b,c]))
        score=max(0.0,raw_score-0.15*disagreement)
        ranked.append({"race_key":key,"horse_number":int(row["horse_number"]),"horse_name":row.get("horse_name"),"probability_winner":round(float(a),6),"probability_top3":round(float(b),6),"probability_top5":round(float(c),6),"ensemble_score":round(score,6),"model_disagreement":round(disagreement,6),"data_completeness":round(completeness,3)})
    ranked.sort(key=lambda x:(-x["ensemble_score"],-x["probability_top3"],x["horse_number"]))
    for i,item in enumerate(ranked,1): item["predicted_rank"]=i

    top_scores=[x["ensemble_score"] for x in ranked[:5]]
    margin=(top_scores[0]-top_scores[1]) if len(top_scores)>1 else 0.0
    disagreement=float(np.mean([x["model_disagreement"] for x in ranked[:5]])) if ranked else 1.0
    confidence="high" if margin>=0.08 and disagreement<0.06 else "medium" if margin>=0.03 and disagreement<0.10 else "low"
    opportunity=score_race_opportunity(ranked)
    result={"prediction_id":f"{key}|{datetime.now(timezone.utc).isoformat()}","generated_at":datetime.now(timezone.utc).isoformat(),"model_version":bundle.get("model_version"),"mode":"v5_market_opportunity_layer","race_key":key,"race":_meta(program),"truth_gate":gate,"press_dependency":False,"post_race_feature_policy":"hard_exclusion","confidence":confidence,"model_agreement":"high" if disagreement<0.06 else "medium" if disagreement<0.10 else "low","recommended_numbers":[x["horse_number"] for x in ranked[:5]],"final_five":[x["horse_number"] for x in ranked[:5]],"ranked_horses":ranked,"race_opportunity":opportunity,"selection_policy":"independent_evidence_ensemble_with_disagreement_penalty_plus_race_opportunity"}
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
