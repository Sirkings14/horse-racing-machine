from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path
from typing import Any
import numpy as np
from src.dataset.program_history import load_program_history
from src.model.historical_profile import build_walk_forward_profiles
from src.model.v3_model import fit_v3_model, known_binary_targets

BASE_DIR=Path(__file__).resolve().parents[1]
DATASET_FILE=BASE_DIR/"data/dataset/training_dataset_clean.json"
OUTPUT_FILE=BASE_DIR/"data/evaluation/jockey_trainer_ablation.json"
PERSONNEL_FIELDS=("jockey_history_starts","jockey_history_win_rate","jockey_history_top3_rate","jockey_history_top5_rate","trainer_history_starts","trainer_history_win_rate","trainer_history_top3_rate","trainer_history_top5_rate")

def _label(row:dict[str,Any], field:str)->int|None:
    idx,labels=known_binary_targets([row],field)
    return labels[0] if idx else None

def _score(model, rows:list[dict[str,Any]])->dict[str,Any]:
    grouped=defaultdict(list)
    for row in rows:
        if row.get("race_key"): grouped[str(row["race_key"])].append(row)
    complete={k:g for k,g in grouped.items() if g and all(_label(r,"top3") is not None for r in g)}
    if not complete: raise ValueError("No holdout races with complete verified top3 labels.")
    # The production feature builder computes race-relative features from the
    # rows passed to predict_proba. Score each race as a separate field, just
    # as a live prediction does; batching unrelated races would change features.
    probabilities_by_race={
        k:np.asarray(model.predict_proba(complete[k]),dtype=float)
        for k in sorted(complete)
    }
    eval_rows=[r for k in sorted(complete) for r in complete[k]]
    p=np.concatenate([probabilities_by_race[k] for k in sorted(complete)])
    y=np.asarray([_label(r,"top3") for r in eval_rows],dtype=float)
    if p.shape != y.shape: raise ValueError(f"Prediction/label shape mismatch: {p.shape} vs {y.shape}")
    brier=float(np.mean((p-y)**2))
    pc=np.clip(p,1e-12,1-1e-12)
    logloss=float(-np.mean(y*np.log(pc)+(1-y)*np.log(1-pc)))
    cov3=[];cov5=[];hit3=[]
    for k in sorted(complete):
        g=complete[k]
        race_p=probabilities_by_race[k]
        if len(race_p)!=len(g): raise ValueError(f"Prediction count mismatch for race {k}")
        ranked=sorted(zip(race_p,g),key=lambda x:(-float(x[0]),int(x[1].get("horse_number") or 9999)))
        actual={int(r["horse_number"]) for r in g if _label(r,"top3")==1 and r.get("horse_number") is not None}
        top3={int(r["horse_number"]) for _,r in ranked[:3] if r.get("horse_number") is not None}
        top5={int(r["horse_number"]) for _,r in ranked[:5] if r.get("horse_number") is not None}
        cov3.append(len(actual&top3));cov5.append(len(actual&top5));hit3.append(bool(actual&top3))
    return {"holdout_rows":len(eval_rows),"holdout_races":len(complete),"top3_brier_per_runner":round(brier,6),"top3_logloss_per_runner":round(logloss,6),"mean_actual_top3_covered_by_predicted_top3":round(float(np.mean(cov3)),6),"mean_actual_top3_covered_by_predicted_top5":round(float(np.mean(cov5)),6),"races_with_at_least_one_actual_top3_in_predicted_top3":round(float(np.mean(hit3)),6)}
def compare(rows:list[dict[str,Any]],epochs:int=900,max_train_rows:int=25000)->dict[str,Any]:
    if not rows: raise ValueError("Historical dataset is empty.")
    cutoff=str(max((r.get("date") or "") for r in rows))[:10]
    profiled=build_walk_forward_profiles(load_program_history(exclude_on_or_after=cutoff)+rows)
    groups=defaultdict(list)
    for r in profiled:
        if r.get("race_key") and not r.get("_program_only_history"):groups[str(r["race_key"])].append(r)
    keys=sorted(groups,key=lambda k:min((str(r.get("date") or "")[:10],k) for r in groups[k]))
    if len(keys)<20:raise ValueError(f"Too few races for chronological holdout: {len(keys)}")
    split=max(1,min(len(keys)-1,int(len(keys)*.8)))
    train_keys,holdout_keys=keys[:split],keys[split:]
    train=[r for k in train_keys for r in groups[k]][-max_train_rows:]
    holdout=[r for k in holdout_keys for r in groups[k]]
    _,labels=known_binary_targets(train,"top3")
    if len(set(labels))<2:raise ValueError("Training split lacks both top3 label classes.")
    baseline_train=[{**r,**{f:0 for f in PERSONNEL_FIELDS}} for r in train]
    baseline_holdout=[{**r,**{f:0 for f in PERSONNEL_FIELDS}} for r in holdout]
    baseline=fit_v3_model(baseline_train,target_field="top3",epochs=epochs)
    challenger=fit_v3_model(train,target_field="top3",epochs=epochs)
    b=_score(baseline,baseline_holdout); c=_score(challenger,holdout)
    return {"status":"completed","method":"chronological 80/20 race-level holdout; same labels, split, training cap and epochs","training_races":len(train_keys),"training_rows_used":len(train),"holdout_races_before_label_filter":len(holdout_keys),"epochs":epochs,"baseline_without_jockey_trainer_features":b,"challenger_with_jockey_trainer_features":c,"delta_challenger_minus_baseline":{k:round(c[k]-b[k],6) for k in ("top3_brier_per_runner","top3_logloss_per_runner","mean_actual_top3_covered_by_predicted_top3","mean_actual_top3_covered_by_predicted_top5")},"interpretation":"Negative Brier/logloss is better; positive coverage deltas are better. This is predictive validation only, not proof of betting profitability."}

def main():
    report=compare(json.loads(DATASET_FILE.read_text(encoding="utf-8")))
    OUTPUT_FILE.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps(report,indent=2,ensure_ascii=False))
if __name__=="__main__":main()
