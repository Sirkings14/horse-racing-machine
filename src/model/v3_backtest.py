from __future__ import annotations
from collections import defaultdict
from typing import Any
import math
import random

from src.model.historical_profile import build_walk_forward_profiles
from src.model.v3_model import fit_v3_model
from src.model.calibration import calibration_metrics

def _key(row): return str(row.get("race_key") or "")
def _sort(row): return (str(row.get("date") or "")[:10],_key(row))

def _valid_rows(rows):
    # Keep the complete race field. Unfinished/non-starter rows are still
    # valid pre-race candidates; only races without a verified outcome are
    # excluded from evaluation later.
    return [r for r in rows if _key(r)]

def _evaluate(ranked):
    winner=next((int(r["horse_number"]) for r in ranked if int(r.get("won",0))==1),None)
    actual={int(r["horse_number"]) for r in ranked if int(r.get("top3",0))==1}
    top3={int(r["horse_number"]) for r in ranked[:3]}
    top5={int(r["horse_number"]) for r in ranked[:5]}
    field=max(len(ranked),1)
    # Expected random Top-3 coverage is 9/field for a 3-runner prediction
    # under a simple uniform benchmark.
    random_top3_coverage=min(3.0,3.0*len(actual)/field)
    return {
        "winner_hit_at_1":bool(ranked and winner==int(ranked[0]["horse_number"])),
        "winner_hit_at_3":bool(winner in top3) if winner is not None else False,
        "top3_coverage_by_top3":len(actual&top3),
        "top3_coverage_by_top5":len(actual&top5),
        "random_expected_top3_coverage":random_top3_coverage,
    }

def _bootstrap_mean(values,seed=17,iterations=1000):
    if not values:return {"mean":None,"lower":None,"upper":None}
    rng=random.Random(seed); n=len(values); means=[]
    for _ in range(iterations):
        sample=[values[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample)/n)
    means.sort()
    return {"mean":round(sum(values)/n,6),"lower":round(means[int(0.025*iterations)],6),"upper":round(means[int(0.975*iterations)-1],6)}

def run(rows:list[dict[str,Any]],min_train_races:int=100,refit_every_days:int=365,max_train_rows:int=25000,epochs:int=20,max_eval_races:int=3000)->dict[str,Any]:
    rows=_valid_rows(rows)
    profiled = rows if rows and "history_starts" in rows[0] else build_walk_forward_profiles(rows)
    groups=defaultdict(list)
    for row in profiled: groups[_key(row)].append(row)
    keys=sorted(groups,key=lambda k:min(_sort(r) for r in groups[k]))
    # Keep validation chronological but bounded. All earlier races remain
    # available for training; only the final holdout window is scored.
    evaluation_keys=set(keys[-max_eval_races:]) if max_eval_races and len(keys)>max_eval_races else set(keys)
    predictions=[]; probabilities=[]; labels=[]
    # Refit once per calendar date, preserving the rule that same-day races
    # cannot teach one another while making large walk-forward validation viable.
    date_to_keys=defaultdict(list)
    for key in keys:
        row=min(groups[key], key=lambda r: _sort(r))
        date_to_keys[str(row.get("date") or "")[:10]].append(key)
    dates=sorted(date_to_keys)
    models=None
    for di,date in enumerate(dates):
        if di < min_train_races: continue
        if models is None or (di - min_train_races) % max(refit_every_days,1) == 0:
            prior_keys=[k for d in dates[:di] for k in date_to_keys[d]]
            train=[r for k in prior_keys for r in groups[k]]
            if len(train) > max_train_rows:
                train = train[-max_train_rows:]
            models={}
            try:
                models["winner"]=fit_v3_model(train,target_field="won",epochs=epochs)
                models["top3"]=fit_v3_model(train,target_field="top3",epochs=epochs)
                models["top5"]=fit_v3_model(train,target_field="top5",epochs=epochs)
            except ValueError:
                continue
        for key in date_to_keys[date]:
            if key not in evaluation_keys:
                continue
            test=groups[key]
            p1=models["winner"].predict_proba(test); p3=models["top3"].predict_proba(test); p5=models["top5"].predict_proba(test)
            ensemble=[0.25*a+0.50*b+0.25*c for a,b,c in zip(p1,p3,p5)]
            ranked=sorted((dict(r,ensemble_score=float(s),p_winner=float(a),p_top3=float(b),p_top5=float(c)) for r,a,b,c,s in zip(test,p1,p3,p5,ensemble)),key=lambda r:(-r["ensemble_score"],int(r.get("horse_number",9999))))
            ev=_evaluate(ranked); ev["race_key"]=key; ev["field_size"]=len(ranked)
            ev["top5_candidates"]=[{
                "horse_number":int(r["horse_number"]),
                "ensemble_score":float(r["ensemble_score"]),
                "probability_winner":float(r.get("p_winner",0.0)),
                "probability_top3":float(r.get("p_top3",0.0)),
                "probability_top5":float(r.get("p_top5",0.0)),
                "won":int(r.get("won",0)),
                **{k:r.get(k) for k in ("win_odds_decimal","decimal_odds","starting_price_decimal","starting_price","win_odds","odds","press_paris_turf_fractional","press_paris_turf_decimal","press_tierce_magazine_fractional","press_tierce_magazine_decimal","press_odds_status")}
            } for r in ranked[:5]]
            predictions.append(ev)
            probabilities.extend(float(x) for x in p3); labels.extend(int(r.get("top3",0)) for r in test)

    n=len(predictions)
    if not n:raise ValueError("V3 backtest produced no evaluable races.")
    winner1=[float(x["winner_hit_at_1"]) for x in predictions]
    winner3=[float(x["winner_hit_at_3"]) for x in predictions]
    cov3=[float(x["top3_coverage_by_top3"]) for x in predictions]
    cov5=[float(x["top3_coverage_by_top5"]) for x in predictions]
    random_cov=[float(x["random_expected_top3_coverage"]) for x in predictions]
    cal=calibration_metrics(probabilities,labels)
    prevalence=(sum(labels)/len(labels)) if labels else 0.0
    brier_baseline=prevalence*(1.0-prevalence)
    logloss_baseline=-(prevalence*math.log(max(prevalence,1e-6))+(1-prevalence)*math.log(max(1-prevalence,1e-6)))

    # Time stability: divide the holdout sequence into up to four chronological blocks.
    block_metrics=[]
    block_count=min(4,max(1,n//25))
    if block_count:
        for b in range(block_count):
            lo=(n*b)//block_count; hi=(n*(b+1))//block_count
            chunk=predictions[lo:hi]
            if not chunk:continue
            block_metrics.append({
                "block":b+1,
                "races":len(chunk),
                "winner_hit_rate_at_1":round(sum(x["winner_hit_at_1"] for x in chunk)/len(chunk),4),
                "winner_hit_rate_at_3":round(sum(x["winner_hit_at_3"] for x in chunk)/len(chunk),4),
                "top3_coverage":round(sum(x["top3_coverage_by_top3"] for x in chunk)/len(chunk),4),
            })

    report={
        "method":"walk_forward_v4_race_relative_no_press",
        "refit_every_days":refit_every_days,
        "dataset_races":len(keys),
        "evaluated_races":n,
        "press_dependency":False,
        "post_race_feature_policy":"hard_exclusion",
        "metrics":{
            "winner_hit_rate_at_1":round(sum(winner1)/n,4),
            "winner_hit_rate_at_3":round(sum(winner3)/n,4),
            "average_actual_top3_covered_by_predicted_top3":round(sum(cov3)/n,4),
            "average_actual_top3_covered_by_predicted_top5":round(sum(cov5)/n,4),
            "random_baseline_top3_coverage":round(sum(random_cov)/n,4),
            **{f"{k}_top3":v for k,v in cal.items()},
            "brier_baseline_top3":round(brier_baseline,6),
            "log_loss_baseline_top3":round(logloss_baseline,6),
            "coverage3_lift_vs_random":round((sum(cov3)/n)/(sum(random_cov)/n)-1.0,4) if sum(random_cov)>0 else None,
        },
        "confidence_intervals":{
            "winner_hit_rate_at_1":_bootstrap_mean(winner1),
            "winner_hit_rate_at_3":_bootstrap_mean(winner3),
            "top3_coverage":_bootstrap_mean(cov3),
        },
        "time_stability":block_metrics,
        "race_results":predictions,
    }
    return report

def main():
    import json
    from pathlib import Path
    base=Path(__file__).resolve().parents[2]; data=json.loads((base/"data/dataset/training_dataset_clean.json").read_text(encoding="utf-8"))
    report=run(data); (base/"data/model").mkdir(parents=True,exist_ok=True)
    (base/"data/model/v3_backtest_report.json").write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps(report["metrics"],indent=2))
if __name__=="__main__":main()
