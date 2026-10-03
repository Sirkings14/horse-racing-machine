from __future__ import annotations
from typing import Any, Iterable
import math

ODDS_FIELDS=("win_odds_decimal","decimal_odds","starting_price_decimal","starting_price","win_odds","odds")

def _decimal_odds(row:dict[str,Any])->float|None:
    for key in ODDS_FIELDS:
        value=row.get(key)
        if value in (None,""): continue
        try:
            x=float(value)
            if x>1.0 and x<1000.0: return x
        except (TypeError,ValueError): pass
    return None

def evaluate_value_strategy(races:Iterable[list[dict[str,Any]]], edge_threshold:float=0.08)->dict[str,Any]:
    """Evaluate only rows with an explicit pre-race decimal price.

    This deliberately refuses to manufacture prices from post-race dividends or
    press text. It is a safety gate for real-stakes deployment, not a claim
    that a predictive model is profitable.
    """
    bets=[]; missing=0
    for ranked in races:
        for row in ranked[:5]:
            odds=_decimal_odds(row)
            p=row.get("ensemble_score")
            if odds is None or p is None:
                missing+=1; continue
            p=float(p); implied=1.0/odds; edge=p-implied
            if edge < edge_threshold: continue
            won=int(row.get("won",0))==1
            profit=(odds-1.0) if won else -1.0
            bets.append((profit,edge,won))
    if not bets:
        return {"status":"insufficient_price_data","bets":0,"coverage_missing_price_rows":missing}
    profit=sum(x[0] for x in bets)
    return {
        "status":"available",
        "bets":len(bets),
        "profit_flat_stake":round(profit,4),
        "roi":round(profit/len(bets),4),
        "win_rate":round(sum(x[2] for x in bets)/len(bets),4),
        "average_edge":round(sum(x[1] for x in bets)/len(bets),4),
        "coverage_missing_price_rows":missing,
        "edge_threshold":edge_threshold,
    }
