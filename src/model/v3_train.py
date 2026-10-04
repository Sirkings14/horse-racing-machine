from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path
from src.model.historical_profile import build_walk_forward_profiles
from src.model.v3_model import fit_v3_model
from src.model.calibration import fit_sigmoid_calibrator, calibration_metrics
from src.model.v3_backtest import run as run_v3_backtest
from src.model.backtest import run_backtest as run_legacy_backtest
from src.model.economic_validation import evaluate_value_strategy

BASE_DIR=Path(__file__).resolve().parents[2]
DATASET_FILE=BASE_DIR/"data/dataset/training_dataset_clean.json"
OUTPUT_FILE=BASE_DIR/"data/model/v3_models.json"

def _promotion_decision(v3m:dict, n_races:int)->tuple[bool,list[str]]:
    reasons=[]
    if n_races<100: reasons.append("too_few_walk_forward_races")
    if v3m.get("winner_hit_rate_at_3",0.0)<0.25: reasons.append("winner_top3_below_minimum")
    if v3m.get("coverage3_lift_vs_random",-1.0)<0.10: reasons.append("top3_coverage_lift_vs_random_too_small")
    if v3m.get("brier_top3") is None or v3m.get("brier_top3") >= v3m.get("brier_baseline_top3",1.0)*0.98:
        reasons.append("top3_probability_model_does_not_beat_constant_baseline")
    if v3m.get("ece_top3") is None or v3m.get("ece_top3")>0.10:
        reasons.append("probability_calibration_too_weak")
    blocks=v3m.get("time_stability") or []
    if len(blocks)>=3:
        block_cov=[float(b.get("top3_coverage",0.0)) for b in blocks]
        overall=float(v3m.get("average_actual_top3_covered_by_predicted_top3",0.0))
        if sum(x>=overall*0.80 for x in block_cov)/len(block_cov)<0.75:
            reasons.append("time_instability")
    return not reasons,reasons

def main():
    rows=json.loads(DATASET_FILE.read_text(encoding="utf-8"))
    if not isinstance(rows,list) or not rows: raise ValueError("Verified training dataset is empty.")
    profiled=build_walk_forward_profiles(rows)
    groups=defaultdict(list)
    for row in profiled:
        if row.get("race_key"): groups[str(row["race_key"])].append(row)
    keys=sorted(groups,key=lambda k:min((str(r.get("date") or "")[:10],k) for r in groups[k]))
    split=max(1,int(len(keys)*0.8))
    train_rows=[r for k in keys[:split] for r in groups[k]]
    cal_rows=[r for k in keys[split:] for r in groups[k]]
    models={}
    calibration_reports={}
    for name,target in (("winner","won"),("top3","top3"),("top5","top5")):
        base=fit_v3_model(train_rows,target_field=target)
        raw=base.predict_proba(cal_rows)
        labels=[int(r.get(target,0)) for r in cal_rows]
        calibration=fit_sigmoid_calibrator(raw,labels)
        final=fit_v3_model(profiled,target_field=target,epochs=120)
        final.calibration=calibration
        models[name]=final.to_dict()
        calibration_reports[name]=calibration_metrics(raw,labels)
    v3_report=run_v3_backtest(rows,min_train_races=5,refit_every_days=365)
    economic_races=[x.get("top5_candidates",[]) for x in (v3_report.get("race_results") or [])]
    economic_report=evaluate_value_strategy(economic_races,edge_threshold=0.08)
    (BASE_DIR/"data/model/economic_validation_report.json").write_text(json.dumps(economic_report,indent=2),encoding="utf-8")
    legacy_report=run_legacy_backtest(rows,min_train_races=5)
    v3m=v3_report["metrics"]; lm=legacy_report["metrics"]
    approved,reasons=_promotion_decision(v3m,len(v3_report.get("race_results") or []))
    # Economic validation is intentionally separate. Predictive accuracy is not
    # treated as proof of betting profitability without historical prices/dividends.
    payload={
        "model_version":"v4-evidence-no-press",
        "press_dependency":False,
        "post_race_feature_policy":"hard_exclusion",
        "calibration_method":"out_of_sample_sigmoid",
        "calibration_races":len(keys)-split,
        "production_approved":approved,
        "economic_validation_status":economic_report.get("status"),
        "economic_validation_report":economic_report,
        "promotion_gate":{
            "approved":approved,
            "reasons":reasons,
            "comparison":"strict_walk_forward_predictive_and_calibration_gate",
            "v4_metrics":v3m,
            "legacy_benchmark":lm,
            "calibration_reports":calibration_reports,
            "required":["minimum_100_holdout_races","winner_top3_minimum","top3_lift_vs_random","brier_beats_constant_baseline","ece_under_0.10","temporal_stability"]
        },
        "models":models
    }
    OUTPUT_FILE.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps({"production_approved":approved,"reasons":reasons,"metrics":v3m},indent=2))

if __name__=="__main__":main()
