from __future__ import annotations
from collections import defaultdict
from typing import Any
from src.model.historical_profile import build_walk_forward_profiles
from src.model.v3_model import fit_v3_model
from src.model.calibration import calibration_metrics

def _key(row): return str(row.get("race_key") or "")
def _sort(row): return (str(row.get("date") or "")[:10],_key(row))

def _valid_rows(rows):
    # Invalid/missing distances are retained as unknown context, never treated as real distances.
    return [r for r in rows if _key(r) and r.get("finish_position") is not None]

def _evaluate(ranked):
    winner=next((int(r["horse_number"]) for r in ranked if int(r.get("won",0))==1),None)
    actual={int(r["horse_number"]) for r in ranked if int(r.get("top3",0))==1}
    top3={int(r["horse_number"]) for r in ranked[:3]}
    top5={int(r["horse_number"]) for r in ranked[:5]}
    return {
        "winner_hit_at_1":bool(ranked and winner==int(ranked[0]["horse_number"])),
        "winner_hit_at_3":bool(winner in top3),
        "top3_coverage_by_top3":len(actual&top3),
        "top3_coverage_by_top5":len(actual&top5),
    }

def run(rows:list[dict[str,Any]],min_train_races:int=50)->dict[str,Any]:
    rows=_valid_rows(rows)
    profiled=build_walk_forward_profiles(rows); groups=defaultdict(list)
    for row in profiled: groups[_key(row)].append(row)
    keys=sorted(groups,key=lambda k:min(_sort(r) for r in groups[k]))
    predictions=[]; probabilities=[]; labels=[]
    for i,key in enumerate(keys):
        if i<min_train_races:continue
        train=[r for k in keys[:i] for r in groups[k]]; test=groups[key]
        models={}
        try:
            models["winner"]=fit_v3_model(train,target_field="won")
            models["top3"]=fit_v3_model(train,target_field="top3")
            models["top5"]=fit_v3_model(train,target_field="top5")
        except ValueError:continue
        p1=models["winner"].predict_proba(test); p3=models["top3"].predict_proba(test); p5=models["top5"].predict_proba(test)
        ensemble=[0.25*a+0.50*b+0.25*c for a,b,c in zip(p1,p3,p5)]
        ranked=sorted((dict(r,ensemble_score=float(s)) for r,s in zip(test,ensemble)),key=lambda r:(-r["ensemble_score"],int(r.get("horse_number",9999))))
        ev=_evaluate(ranked); ev["race_key"]=key; predictions.append(ev)
        probabilities.extend(float(x) for x in p3); labels.extend(int(r.get("top3",0)) for r in test)
    n=len(predictions)
    if not n:raise ValueError("V3 backtest produced no evaluable races.")
    cal=calibration_metrics(probabilities,labels)
    return {"method":"walk_forward_v3_evidence_no_press","dataset_races":len(keys),"evaluated_races":n,"press_dependency":False,"post_race_feature_policy":"hard_exclusion","metrics":{
        "winner_hit_rate_at_1":round(sum(x["winner_hit_at_1"] for x in predictions)/n,4),
        "winner_hit_rate_at_3":round(sum(x["winner_hit_at_3"] for x in predictions)/n,4),
        "average_actual_top3_covered_by_predicted_top3":round(sum(x["top3_coverage_by_top3"] for x in predictions)/n,4),
        "average_actual_top3_covered_by_predicted_top5":round(sum(x["top3_coverage_by_top5"] for x in predictions)/n,4),
        **{f"{k}_top3":v for k,v in cal.items()}
    },"race_results":predictions}

def main():
    import json
    from pathlib import Path
    base=Path(__file__).resolve().parents[2]; data=json.loads((base/"data/dataset/training_dataset_clean.json").read_text(encoding="utf-8"))
    report=run(data); (base/"data/model").mkdir(parents=True,exist_ok=True)
    (base/"data/model/v3_backtest_report.json").write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps(report["metrics"],indent=2))
if __name__=="__main__":main()
