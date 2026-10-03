from __future__ import annotations
from typing import Any, Sequence
import numpy as np

FEATURE_NAMES=[
"history_starts","history_win_rate","history_top3_rate","history_top5_rate",
"history_recent_top3_rate","history_recent_top5_rate","history_recent_avg_finish_norm",
"course_starts","course_top3_rate","course_top5_rate",
"distance_starts","distance_top3_rate","distance_top5_rate",
"history_avg_finish_norm","days_since_last_run_norm",
"distance_norm","distance_valid","field_size_norm","prize_norm","race_number_norm",
"race_type_flat","race_type_trot","race_type_jump","data_completeness"
]

def _float(value:Any,default:float=0.0)->float:
    try:return float(value)
    except (TypeError,ValueError):return default

def row_to_v3_features(row:dict[str,Any])->list[float]:
    distance=_float(row.get("distance"))
    distance_valid=1.0 if 800<=distance<=7000 else 0.0
    if not distance_valid: distance=0.0
    runners=_float(row.get("runners_count"))
    prize=_float(row.get("prize_euros"))
    race_number=_float(row.get("race_number"))
    weight=_float(row.get("weight") if row.get("weight") is not None else row.get("carried_weight"))
    draw=_float(row.get("draw") if row.get("draw") is not None else row.get("stall"))
    avg=row.get("history_avg_finish")
    avg_norm=0.0 if avg is None else max(0.0,min(1.0,1.0-(_float(avg)-1.0)/19.0))
    recent_avg=row.get("history_recent_avg_finish")
    recent_avg_norm=0.0 if recent_avg is None else max(0.0,min(1.0,1.0-(_float(recent_avg)-1.0)/19.0))
    days=_float(row.get("days_since_last_run"))
    days_norm=0.0 if days<=0 else max(0.0,min(1.0,1.0-abs(days-21.0)/60.0))
    race_type=str(row.get("race_type") or "").upper()
    completeness=sum(row.get(k) not in (None,"") for k in (
        "date","track","distance","runners_count","horse_number","horse_name"
    ))/6.0
    return [
        min(_float(row.get("history_starts"))/20.0,1.0),
        max(0.0,min(1.0,_float(row.get("history_win_rate")))),
        max(0.0,min(1.0,_float(row.get("history_top3_rate")))),
        max(0.0,min(1.0,_float(row.get("history_top5_rate")))),
        max(0.0,min(1.0,_float(row.get("history_recent_top3_rate")))),
        max(0.0,min(1.0,_float(row.get("history_recent_top5_rate")))),
        recent_avg_norm,
        min(_float(row.get("course_starts"))/10.0,1.0),
        max(0.0,min(1.0,_float(row.get("course_top3_rate")))),
        max(0.0,min(1.0,_float(row.get("course_top5_rate")))),
        min(_float(row.get("distance_starts"))/10.0,1.0),
        max(0.0,min(1.0,_float(row.get("distance_top3_rate")))),
        max(0.0,min(1.0,_float(row.get("distance_top5_rate")))),
        avg_norm,days_norm,min(distance/3500.0,1.0),distance_valid,
        min(max(runners/20.0,0.0),1.0),
        min(max(prize/100000.0,0.0),1.0),
        min(max(race_number/12.0,0.0),1.0),
        1.0 if race_type=="PLAT" else 0.0,
        1.0 if race_type in {"ATTELE","MONTE"} else 0.0,
        1.0 if race_type in {"OBSTACLE","HAIES","STEEPLE-CHASE"} else 0.0,
        completeness
    ]

def build_v3_matrix(rows:Sequence[dict[str,Any]])->np.ndarray:
    if not rows:return np.empty((0,len(FEATURE_NAMES)),dtype=float)
    return np.asarray([row_to_v3_features(row) for row in rows],dtype=float)
