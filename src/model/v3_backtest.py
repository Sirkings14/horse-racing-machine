from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path
from typing import Any
from src.model.historical_profile import build_walk_forward_profiles
from src.model.v3_model import fit_v3_model
from src.model.calibration import calibration_metrics

BASE_DIR=Path(__file__).resolve().parents[2]
DATASET_FILE=BASE_DIR/"data/dataset/training_dataset_clean.json"
OUTPUT_FILE=BASE_DIR/"data/model/v3_backtest_report.json"

def _key(row): return str(row.get("race_key") or "")
def _sort(row): return (str(row.get("date") or "")[:10],_key(row))

def run(rows:list[dict[str,Any]],min_train_races:int=50)->dict[str,Any]:
    profiled=build_walk_forward_profiles(rows); groups=defaultdict(list)
    for row in profiled:
        if _key(row): groups[_key(row)].append(row)
    keys=sorted(groups,key=lambda k:min(_sort(r) for r in groups[k])); predictions=[]
    for i,key in enumerate(keys):
        if i<min_train_races: continue
        train=[r for k in keys[:i] for r in groups[k]]; test=groups[key]
        try: p=fit_v3_model(train).predict_proba(test)
        except ValueError: continue
        ranked=sorted(zip(test,p),key=lambda z:(-float(z[1]),int(z[0].get("horse_number",9999))))
        probabilities.extend(float(v) for v in p)
        labels.extend(int(r.get("top3",0)) for r in test)
        winner=next((int(r["horse_number"]) for r,_ in ranked if int(r.get("won",0))==1),None)
        actual={int(r["horse_number"]) for r,_ in ranked if int(r.get("top3",0))==1}
        top3={int(r["horse_number"]) for r,_ in ranked[:3]}; top5={int(r["horse_number"]) for r,_ in ranked[:5]}
        predictions.append({"race_key":key,"winner_hit_at_1":bool(ranked and winner==int(ranked[0][0]["horse_number"])),"winner_hit_at_3":bool(winner in top3),"top3_coverage_by_top3":len(actual&top3),"top3_coverage_by_top5":len(actual&top5)})
    n=len(predictions)
    if not n: raise ValueError("V3 backtest produced no evaluable races.")
    return {"method":"walk_forward_v3_evidence_no_press","dataset_races":len(keys),"evaluated_races":n,"press_dependency":False,"post_race_feature_policy":"hard_exclusion","metrics":{"winner_hit_rate_at_1":round(sum(x["winner_hit_at_1"] for x in predictions)/n,4),"winner_hit_rate_at_3":round(sum(x["winner_hit_at_3"] for x in predictions)/n,4),"average_actual_top3_covered_by_predicted_top3":round(sum(x["top3_coverage_by_top3"] for x in predictions)/n,4),"average_actual_top3_covered_by_predicted_top5":round(sum(x["top3_coverage_by_top5"] for x in predictions)/n,4),**{f"{k}_top3":v for k,v in calibration_metrics(probabilities,labels).items()}},"race_results":predictions}

def main():
    rows=json.loads(DATASET_FILE.read_text(encoding="utf-8")); report=run(rows)
    OUTPUT_FILE.parent.mkdir(parents=True,exist_ok=True); OUTPUT_FILE.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps(report["metrics"],indent=2))
if __name__=="__main__": main()
