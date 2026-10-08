from __future__ import annotations
from typing import Any, Sequence
import numpy as np

# All features are pre-race and press-independent. Race-relative fields are
# calculated only from other runners' pre-race features in the same race.
FEATURE_NAMES=[
"history_starts","history_win_rate","history_top3_rate","history_top5_rate",
"history_recent_top3_rate","history_recent_top5_rate","history_recent_avg_finish_norm",
"course_starts","course_top3_rate","course_top5_rate",
"distance_starts","distance_top3_rate","distance_top5_rate",
"history_avg_finish_norm","days_since_last_run_norm",
"distance_norm","distance_valid","field_size_norm","prize_norm","race_number_norm",
"race_type_flat","race_type_trot","race_type_jump","data_completeness",
"weight_norm","draw_norm","history_win_relative","history_top3_relative",
"history_top5_relative","recent_top3_relative","recent_top5_relative",
"recent_finish_relative","course_top3_relative","distance_top3_relative",
"weight_relative","experience_relative",
"trainer_starts_norm","trainer_win_rate","trainer_top3_rate","trainer_top5_rate",
"trainer_course_win_rate","trainer_course_top3_rate","driver_starts_norm","driver_win_rate",
"driver_top3_rate","driver_top5_rate","driver_course_win_rate","driver_course_top3_rate",
"trainer_win_relative","trainer_top3_relative","driver_win_relative","driver_top3_relative",
"trainer_course_top3_relative","driver_course_top3_relative"
]

def _float(value:Any,default:float=0.0)->float:
    try:return float(value)
    except (TypeError,ValueError):return default

def _clamp(value:float,lo:float=0.0,hi:float=1.0)->float:
    return max(lo,min(hi,float(value)))

def _base_features(row:dict[str,Any])->list[float]:
    distance=_float(row.get("distance"))
    distance_valid=1.0 if 800<=distance<=7000 else 0.0
    if not distance_valid: distance=0.0
    runners=_float(row.get("runners_count"))
    prize=_float(row.get("prize_euros"))
    race_number=_float(row.get("race_number"))
    weight=_float(row.get("weight") if row.get("weight") is not None else row.get("carried_weight"))
    draw=_float(row.get("draw") if row.get("draw") is not None else row.get("stall"))
    avg=row.get("history_avg_finish")
    avg_norm=0.0 if avg is None else _clamp(1.0-(_float(avg)-1.0)/19.0)
    recent_avg=row.get("history_recent_avg_finish")
    recent_avg_norm=0.0 if recent_avg is None else _clamp(1.0-(_float(recent_avg)-1.0)/19.0)
    days=_float(row.get("days_since_last_run"))
    days_norm=0.0 if days<=0 else _clamp(1.0-abs(days-21.0)/60.0)
    race_type=str(row.get("race_type") or "").upper()
    completeness=sum(row.get(k) not in (None,"") for k in (
        "date","track","distance","runners_count","horse_number","horse_name"
    ))/6.0
    # Weight/draw are only informative when the source actually supplies them.
    # Missing values remain neutral rather than being fabricated.
    weight_norm=_clamp(weight/80.0) if weight>0 else 0.0
    draw_norm=_clamp(draw/max(runners,1.0)) if draw>0 and runners>0 else 0.0
    return [
        _clamp(_float(row.get("history_starts"))/20.0),
        _clamp(_float(row.get("history_win_rate"))),
        _clamp(_float(row.get("history_top3_rate"))),
        _clamp(_float(row.get("history_top5_rate"))),
        _clamp(_float(row.get("history_recent_top3_rate"))),
        _clamp(_float(row.get("history_recent_top5_rate"))),
        recent_avg_norm,
        _clamp(_float(row.get("course_starts"))/10.0),
        _clamp(_float(row.get("course_top3_rate"))),
        _clamp(_float(row.get("course_top5_rate"))),
        _clamp(_float(row.get("distance_starts"))/10.0),
        _clamp(_float(row.get("distance_top3_rate"))),
        _clamp(_float(row.get("distance_top5_rate"))),
        avg_norm,days_norm,_clamp(distance/3500.0),distance_valid,
        _clamp(runners/20.0),_clamp(prize/100000.0),_clamp(race_number/12.0),
        1.0 if race_type=="PLAT" else 0.0,
        1.0 if race_type in {"ATTELE","MONTE"} else 0.0,
        1.0 if race_type in {"OBSTACLE","HAIES","STEEPLE-CHASE"} else 0.0,
        completeness,weight_norm,draw_norm,
        _clamp(_float(row.get("trainer_starts"))/50.0),
        _clamp(_float(row.get("trainer_win_rate"))),
        _clamp(_float(row.get("trainer_top3_rate"))),
        _clamp(_float(row.get("trainer_top5_rate"))),
        _clamp(_float(row.get("trainer_course_win_rate"))),
        _clamp(_float(row.get("trainer_course_top3_rate"))),
        _clamp(_float(row.get("driver_starts"))/50.0),
        _clamp(_float(row.get("driver_win_rate"))),
        _clamp(_float(row.get("driver_top3_rate"))),
        _clamp(_float(row.get("driver_top5_rate"))),
        _clamp(_float(row.get("driver_course_win_rate"))),
        _clamp(_float(row.get("driver_course_top3_rate"))),
    ]

def _relative(rows:Sequence[dict[str,Any]])->np.ndarray:
    base=np.asarray([_base_features(r) for r in rows],dtype=float)
    if len(base)==0:return np.empty((0,16),dtype=float)
    # Percentile-like relative strength within the race. A zero-history horse
    # is not treated as weak: its raw prior-history values remain zero while
    # these relative features expose only observed differences.
    cols=[1,2,3,4,5,6,8,11,24,0,27,28,33,34,31,37]
    selected=base[:,cols]
    means=selected.mean(axis=0)
    stds=selected.std(axis=0)
    safe_stds=np.where(stds>1e-9,stds,1.0)
    rel=(selected-means)/safe_stds
    # Map the 16 selected columns into the six explicit participant-relative slots.
    extra=rel[:,10:16]
    return np.concatenate([rel[:,:10],extra],axis=1)

def row_to_v3_features(row:dict[str,Any])->list[float]:
    base=_base_features(row)
    # Individual-row API keeps relative fields neutral. build_v3_matrix is
    # the production path and computes race-relative features from the batch.
    return base+[0.0]*16

def build_v3_matrix(rows:Sequence[dict[str,Any]])->np.ndarray:
    if not rows:return np.empty((0,len(FEATURE_NAMES)),dtype=float)
    base=np.asarray([_base_features(r) for r in rows],dtype=float)
    rel=_relative(rows)
    return np.concatenate([base,rel],axis=1)
