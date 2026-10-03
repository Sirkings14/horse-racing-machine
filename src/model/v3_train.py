from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path
from src.model.historical_profile import build_walk_forward_profiles
from src.model.v3_model import fit_v3_model
from src.model.calibration import fit_sigmoid_calibrator, calibration_metrics
from src.model.v3_backtest import run as run_v3_backtest
from src.model.backtest import run_backtest as run_legacy_backtest
BASE_DIR=Path(__file__).resolve().parents[2]
DATASET_FILE=BASE_DIR/"data/dataset/training_dataset_clean.json"
OUTPUT_FILE=BASE_DIR/"data/model/v3_models.json"

def main():
    rows=json.loads(DATASET_FILE.read_text(encoding="utf-8"))
    profiled=build_walk_forward_profiles(rows)
    groups=defaultdict(list)
    for row in profiled:
        if row.get("race_key"): groups[str(row["race_key"])].append(row)
    keys=sorted(groups,key=lambda k:min((str(r.get("date") or "")[:10],k) for r in groups[k]))
    split=max(1,int(len(keys)*0.8))
    train_rows=[r for k in keys[:split] for r in groups[k]]
    cal_rows=[r for k in keys[split:] for r in groups[k]]
    models={}
    for name,target in (("winner","won"),("top3","top3"),("top5","top5")):
        base=fit_v3_model(train_rows,target_field=target)
        raw=base.predict_proba(cal_rows)
        labels=[int(r.get(target,0)) for r in cal_rows]
        calibration=fit_sigmoid_calibrator(raw,labels)
        final=fit_v3_model(profiled,target_field=target)
        final.calibration=calibration
        models[name]=final.to_dict()
        metrics=calibration_metrics(raw,labels)
        print(name,"calibration",metrics)
    v3_report=run_v3_backtest(rows,min_train_races=max(50,split//2))
    legacy_report=run_legacy_backtest(rows,min_train_races=max(50,split//2))
    v3m=v3_report["metrics"]; lm=legacy_report["metrics"]
    approved=(v3m["winner_hit_rate_at_3"] >= lm["winner_hit_rate_at_3"] and v3m["average_actual_top3_covered_by_predicted_top3"] >= lm["average_actual_top3_covered_by_predicted_top3"])
    payload={"model_version":"v3-evidence-no-press","press_dependency":False,"post_race_feature_policy":"hard_exclusion","calibration_method":"out_of_sample_sigmoid","calibration_races":len(keys)-split,"production_approved":approved,"promotion_gate":{"comparison":"same_walk_forward_horizon","required":["winner_hit_rate_at_3_non_regression","top3_coverage_non_regression"],"v3_metrics":v3m,"legacy_benchmark":lm},"models":models}
    OUTPUT_FILE.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding="utf-8")
    print(f"Saved V3 calibrated model bundle: {OUTPUT_FILE}")

if __name__=="__main__": main()
