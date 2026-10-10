from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path
from src.model.historical_profile import build_walk_forward_profiles, merge_program_history_rows
from src.model.v3_model import fit_v3_model
from src.model.calibration import fit_sigmoid_calibrator, apply_sigmoid_calibrator, calibration_metrics
from src.model.v3_backtest import run as run_v3_backtest
from src.model.backtest import run_backtest as run_legacy_backtest  # legacy benchmark is informational
from src.model.economic_validation import evaluate_value_strategy
from src.dataset.program_history import load_program_history

BASE_DIR=Path(__file__).resolve().parents[2]
DATASET_FILE=BASE_DIR/"data/dataset/training_dataset_clean.json"
OUTPUT_FILE=BASE_DIR/"data/model/v3_models.json"

def _promotion_decision(v3m:dict, n_races:int, calibration_gate:dict|None=None, paired_comparison:dict|None=None)->tuple[bool,list[str]]:
    reasons=[]
    if n_races<100: reasons.append("too_few_walk_forward_races")
    if v3m.get("winner_hit_rate_at_3",0.0)<0.25: reasons.append("winner_top3_below_minimum")
    if v3m.get("coverage3_lift_vs_random",-1.0)<0.10: reasons.append("top3_coverage_lift_vs_random_too_small")
    gate=calibration_gate or v3m
    if gate.get("brier") is None or gate.get("brier") >= gate.get("brier_baseline",1.0)*0.98:
        reasons.append("top3_probability_model_does_not_beat_constant_baseline")
    if gate.get("ece") is None or gate.get("ece")>0.10:
        reasons.append("probability_calibration_too_weak")
    blocks=v3m.get("time_stability") or []
    if len(blocks)>=3:
        block_cov=[float(b.get("top3_coverage",0.0)) for b in blocks]
        overall=float(v3m.get("average_actual_top3_covered_by_predicted_top3",0.0))
        if sum(x>=overall*0.80 for x in block_cov)/len(block_cov)<0.75:
            reasons.append("time_instability")
    paired=paired_comparison or {}
    if paired.get("non_regression_pass") is not True:
        reasons.append("incumbent_reference_non_regression_failed")
    if paired.get("material_uplift_pass") is not True:
        reasons.append("no_material_uplift_over_legacy_feature_reference")
    return not reasons,reasons

def main():
    rows=json.loads(DATASET_FILE.read_text(encoding="utf-8"))
    if not isinstance(rows,list) or not rows: raise ValueError("Verified training dataset is empty.")
    history_rows = load_program_history(exclude_on_or_after=str(rows[-1].get("date") or "")[:10])
    profile_rows, program_history_audit = merge_program_history_rows(rows, history_rows)
    profiled=build_walk_forward_profiles(profile_rows)
    groups=defaultdict(list)
    for row in profiled:
        if row.get("race_key") and not row.get("_program_only_history"): groups[str(row["race_key"])].append(row)
    keys=sorted(groups,key=lambda k:min((str(r.get("date") or "")[:10],k) for r in groups[k]))
    split=max(1,int(len(keys)*0.8))
    train_rows=[r for k in keys[:split] for r in groups[k]]
    cal_rows=[r for k in keys[split:] for r in groups[k]]
    # Keep final fitting bounded; validation remains full walk-forward and unchanged.
    fit_rows=train_rows[-25000:]
    final_rows=[r for r in profiled if not r.get("_program_only_history")][-25000:]
    models={}
    calibration_reports={}
    calibration_validation_reports={}
    # Evaluate calibration on a chronological sample that was not used to fit
    # the calibrator. Bound the calibration samples to keep CI practical.
    cal_split=max(30,int(len(cal_rows)*0.70))
    cal_fit_rows=cal_rows[:cal_split][-60000:]
    cal_eval_rows=cal_rows[cal_split:][-60000:]
    for name,target in (("winner","won"),("top3","top3"),("top5","top5")):
        base=fit_v3_model(fit_rows,target_field=target,epochs=20)
        raw_fit=base.predict_proba(cal_fit_rows)
        labels_fit=[int(r.get(target,0)) for r in cal_fit_rows]
        calibration=fit_sigmoid_calibrator(raw_fit,labels_fit)
        raw_eval=base.predict_proba(cal_eval_rows)
        labels_eval=[int(r.get(target,0)) for r in cal_eval_rows]
        calibrated_eval=[apply_sigmoid_calibrator(v,calibration) for v in raw_eval]
        validation=calibration_metrics(calibrated_eval,labels_eval)
        prevalence=(sum(labels_eval)/len(labels_eval)) if labels_eval else 0.0
        validation["brier_baseline"]=round(prevalence*(1.0-prevalence),6)
        final=fit_v3_model(final_rows,target_field=target,epochs=20)
        final.calibration=calibration
        models[name]=final.to_dict()
        calibration_reports[name]=calibration_metrics(raw_fit,labels_fit)
        calibration_validation_reports[name]=validation
    # Reuse the walk-forward report produced by the validation workflow. Re-running
    # the full backtest here duplicated the most expensive CI stage and could exhaust
    # the GitHub Actions job limit without changing the promotion decision.
    report_file=BASE_DIR/"data/model/v3_backtest_report.json"
    if report_file.exists():
        v3_report=json.loads(report_file.read_text(encoding="utf-8"))
    else:
        v3_report=run_v3_backtest(rows,min_train_races=5,refit_every_days=365)
    economic_races=[x.get("top5_candidates",[]) for x in (v3_report.get("race_results") or [])]
    economic_report=evaluate_value_strategy(economic_races,edge_threshold=0.08)
    (BASE_DIR/"data/model/economic_validation_report.json").write_text(json.dumps(economic_report,indent=2),encoding="utf-8")
    # The legacy walk-forward benchmark is informational only and is quadratic in
    # race count. Reuse the checked-in benchmark when available instead of blocking
    # V4 promotion on an unrelated legacy computation.
    legacy_file=BASE_DIR/"data/model/backtest_report.json"
    if legacy_file.exists():
        legacy_report=json.loads(legacy_file.read_text(encoding="utf-8"))
    else:
        legacy_report={"metrics":{}, "status":"not_recomputed_in_v4_validation"}
    v3m=v3_report["metrics"]; lm=legacy_report["metrics"]
    calibration_gate=calibration_validation_reports.get("top3") or {}
    paired_comparison=v3_report.get("paired_comparison") or {}
    approved,reasons=_promotion_decision(v3m,len(v3_report.get("race_results") or []),calibration_gate=calibration_gate,paired_comparison=paired_comparison)
    # Economic validation is intentionally separate. Predictive accuracy is not
    # treated as proof of betting profitability without historical prices/dividends.
    payload={
        "model_version":"v4-evidence-no-press",
        "press_dependency":False,
        "post_race_feature_policy":"hard_exclusion",
        "calibration_method":"out_of_sample_sigmoid",
        "program_history_merge_audit":program_history_audit,
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
            "calibration_validation_reports":calibration_validation_reports,
            "calibration_gate":calibration_gate,
            "paired_comparison":paired_comparison,
            "required":["minimum_100_holdout_races","winner_top3_minimum","top3_lift_vs_random","brier_beats_constant_baseline","ece_under_0.10","temporal_stability"]
        },
        "models":models
    }
    OUTPUT_FILE.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps({"production_approved":approved,"reasons":reasons,"metrics":v3m},indent=2))

if __name__=="__main__":main()
