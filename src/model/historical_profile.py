from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
import re
import unicodedata
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
    try:return date.fromisoformat(str(row.get("date") or "")[:10])
    except ValueError:return None

def _date_key(row): return str(row.get("date") or "")[:10]

_ID_FIELDS=("horse_id","horseId","horse_uid","horseUid","idCheval","id_cheval","identifiantCheval","identifiant_cheval")

def _clean_name(value:Any)->str:
    text=unicodedata.normalize("NFKD",str(value or ""))
    text="".join(ch for ch in text if not unicodedata.combining(ch))
    text=text.upper().replace("’","'").replace("–","-").replace("—","-")
    text=re.sub(r"[^A-Z0-9]+"," ",text)
    return re.sub(r"\s+"," ",text).strip()

def _horse_key(row:dict[str,Any])->str:
    for field_name in _ID_FIELDS:
        value=row.get(field_name)
        if value not in (None,""):
            return "ID:"+str(value).strip()
    name=_clean_name(row.get("horse_name") or row.get("horse"))
    return "NAME:"+name if name else ""

def horse_identity_source(row:dict[str,Any])->str:
    return "stable_id" if any(row.get(k) not in (None,"") for k in _ID_FIELDS) else "normalized_name"

def _distance(row):
    try:
        value=int(float(row.get("distance")))
        return value if 800<=value<=7000 else None
    except (TypeError,ValueError):return None

def _finish(row):
    for key in ("finish_position","position","finish"):
        try:
            value=int(row.get(key))
            if value>0:return value
        except (TypeError,ValueError):pass
    return None

def _bucket(distance:int|None)->int|None:
    return None if distance is None else int(round(distance/100.0)*100)

def _stats(history:HorseHistory,track:str|None,distance:int|None):
    course=history.course_stats.get(str(track or "").upper(),[0,0,0])
    ds=dt=dt5=0
    if distance is not None:
        center=_bucket(distance)
        for delta in (-200,-100,0,100,200):
            stats=history.distance_stats.get(center+delta)
            if stats:
                starts,top3,top5=stats
                ds+=starts; dt+=top3; dt5+=top5
    return course,ds,dt,dt5

def build_walk_forward_profiles(rows:Iterable[dict[str,Any]])->list[dict[str,Any]]:
    """Build only information that existed before each race; same-date races cannot teach one another."""
    rows_list=list(rows)
    ordered=list(enumerate(rows_list))
    if any(
        (_date_key(ordered[i][1]),str(ordered[i][1].get("race_key") or ""),ordered[i][0])
        > (_date_key(ordered[i+1][1]),str(ordered[i+1][1].get("race_key") or ""),ordered[i+1][0])
        for i in range(len(ordered)-1)
    ):
        ordered.sort(key=lambda item:(_date_key(item[1]),str(item[1].get("race_key") or ""),item[0]))
    histories:dict[str,HorseHistory]=defaultdict(HorseHistory)
    output=[]; index=0
    while index<len(ordered):
        current_date=_date_key(ordered[index][1]); end=index
        while end<len(ordered) and _date_key(ordered[end][1])==current_date:end+=1
        for _,row in ordered[index:end]:
            key=_horse_key(row)
            h=histories[key]; recent=h.recent_finishes[-5:]
            course,ds,dt,dt5=_stats(h,row.get("track"),_distance(row))
            recent_avg=sum(recent)/len(recent) if recent else None
            output.append({**row,
                "horse_identity_source":horse_identity_source(row),
                "history_starts":h.starts,
                "history_win_rate":h.wins/h.starts if h.starts else 0.0,
                "history_top3_rate":h.top3/h.starts if h.starts else 0.0,
                "history_top5_rate":h.top5/h.starts if h.starts else 0.0,
                "history_avg_finish":h.finish_sum/h.starts if h.starts else None,
                "history_recent_top3_rate":sum(x<=3 for x in recent)/len(recent) if recent else 0.0,
                "history_recent_top5_rate":sum(x<=5 for x in recent)/len(recent) if recent else 0.0,
                "history_recent_avg_finish":recent_avg,
                "course_starts":course[0],
                "course_top3_rate":course[1]/course[0] if course[0] else 0.0,
                "course_top5_rate":course[2]/course[0] if course[0] else 0.0,
                "distance_starts":ds,
                "distance_top3_rate":dt/ds if ds else 0.0,
                "distance_top5_rate":dt5/ds if ds else 0.0,
                "days_since_last_run":((_date_value(row)-h.last_date).days if _date_value(row) and h.last_date else None),
            })
        for _,row in ordered[index:end]:
            key=_horse_key(row); finish=_finish(row)
            if not key or finish is None:continue
            h=histories[key]; track=str(row.get("track") or "").upper(); distance=_distance(row); d=_date_value(row)
            h.starts+=1; h.wins+=finish==1; h.top3+=finish<=3; h.top5+=finish<=5; h.finish_sum+=finish
            h.recent_finishes=(h.recent_finishes+[finish])[-10:]
            if d:h.last_date=d
            if track:
                s=h.course_stats.setdefault(track,[0,0,0]); s[0]+=1; s[1]+=finish<=3; s[2]+=finish<=5
            bucket=_bucket(distance)
            if bucket is not None:
                s=h.distance_stats.setdefault(bucket,[0,0,0]); s[0]+=1; s[1]+=finish<=3; s[2]+=finish<=5
        index=end
    return output
