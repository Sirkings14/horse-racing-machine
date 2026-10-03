from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable

@dataclass
class HorseHistory:
    starts:int=0
    wins:int=0
    top3:int=0
    top5:int=0
    finish_sum:float=0.0
    recent_finishes:list[int]=field(default_factory=list)
    last_date:date|None=None
    course_stats:dict[str,list[int]]=field(default_factory=dict)
    distance_stats:dict[int,list[int]]=field(default_factory=dict)

def _date_value(row:dict[str,Any])->date|None:
    try: return date.fromisoformat(str(row.get("date") or "")[:10])
    except ValueError: return None

def _date_key(row): return str(row.get("date") or "")[:10]
def _horse_key(row): return str(row.get("horse_name") or row.get("horse") or "").strip().upper()

def _distance(row):
    try:
        value=int(float(row.get("distance")))
        return value if 800<=value<=7000 else None
    except (TypeError,ValueError): return None

def _finish(row):
    for key in ("finish_position","position","finish"):
        try:
            value=int(row.get(key))
            if value>0: return value
        except (TypeError,ValueError): pass
    return None

def _bucket(distance:int|None)->int|None:
    if distance is None: return None
    return int(round(distance/100.0)*100)

def _stats(history:HorseHistory, track:str|None, distance:int|None):
    course=history.course_stats.get(str(track or "").upper(),[0,0])
    distance_stats=[]
    if distance is not None:
        for bucket,(starts,top3) in history.distance_stats.items():
            if abs(bucket-distance)<=250:
                distance_stats.append((starts,top3))
    ds=sum(x[0] for x in distance_stats); dt=sum(x[1] for x in distance_stats)
    return course,ds,dt

def build_walk_forward_profiles(rows:Iterable[dict[str,Any]])->list[dict[str,Any]]:
    """Create strictly prior-race features; same-date races cannot teach one another."""
    ordered=sorted(enumerate(rows),key=lambda item:(_date_key(item[1]),str(item[1].get("race_key") or ""),item[0]))
    histories:dict[str,HorseHistory]=defaultdict(HorseHistory)
    output=[]; index=0
    while index<len(ordered):
        current_date=_date_key(ordered[index][1]); end=index
        while end<len(ordered) and _date_key(ordered[end][1])==current_date: end+=1
        for _,row in ordered[index:end]:
            h=histories[_horse_key(row)]; recent=h.recent_finishes[-5:]
            course,ds,dt=_stats(h,row.get("track"),_distance(row))
            output.append({**row,
                "history_starts":h.starts,
                "history_win_rate":h.wins/h.starts if h.starts else 0.0,
                "history_top3_rate":h.top3/h.starts if h.starts else 0.0,
                "history_top5_rate":h.top5/h.starts if h.starts else 0.0,
                "history_avg_finish":h.finish_sum/h.starts if h.starts else None,
                "history_recent_top3_rate":sum(x<=3 for x in recent)/len(recent) if recent else 0.0,
                "history_recent_top5_rate":sum(x<=5 for x in recent)/len(recent) if recent else 0.0,
                "course_starts":course[0],
                "course_top3_rate":course[1]/course[0] if course[0] else 0.0,
                "distance_starts":ds,
                "distance_top3_rate":dt/ds if ds else 0.0,
                "days_since_last_run":((_date_value(row)-h.last_date).days if _date_value(row) and h.last_date else None),
            })
        for _,row in ordered[index:end]:
            key=_horse_key(row); finish=_finish(row)
            if not key or finish is None: continue
            h=histories[key]; track=str(row.get("track") or "").upper(); distance=_distance(row); d=_date_value(row)
            h.starts+=1; h.wins+=finish==1; h.top3+=finish<=3; h.top5+=finish<=5; h.finish_sum+=finish
            h.recent_finishes=(h.recent_finishes+[finish])[-10:]
            if d: h.last_date=d
            if track:
                s=h.course_stats.setdefault(track,[0,0]); s[0]+=1; s[1]+=finish<=3
            bucket=_bucket(distance)
            if bucket is not None:
                s=h.distance_stats.setdefault(bucket,[0,0]); s[0]+=1; s[1]+=finish<=3
        index=end
    return output
