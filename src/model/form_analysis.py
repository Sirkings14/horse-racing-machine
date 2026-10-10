"""Conservative parser for the pre-race form strings shown on racing cards.

This module reports auditable statistics only. It deliberately does not turn a
parsed form string into a betting score; discipline-specific validation and
out-of-sample tests are required before form statistics can enter the model.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any


# These markers are retained as statuses, not over-interpreted as a specific
# incident. The exact meaning can differ by code system and discipline.
_STATUS_MARKERS = {
    "D", "DA", "DAI", "DI", "DISQ", "A", "AR", "T", "TH", "F", "P", "PU",
    "UR", "U", "R", "RO", "BD", "NP", "NPO", "AB", "ABD", "SU", "RET",
}
_TOKEN_SPLIT = re.compile(r"[.\s,/;|]+")
_FINISH_TOKEN = re.compile(r"(\d{1,2})(?:[A-Z]{1,3})?")


def _normal_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.upper().replace("’", "'").strip()


def tokenize_form(value: Any) -> list[str]:
    """Split a form string while keeping each result/status token intact."""
    if value in (None, ""):
        return []
    if isinstance(value, (list, tuple)):
        raw = " ".join(str(item) for item in value if item not in (None, ""))
    else:
        raw = str(value)
    normalized = _normal_text(raw)
    return [token for token in _TOKEN_SPLIT.split(normalized) if token]


def analyze_form(value: Any, race_type: Any = None) -> dict[str, Any]:
    """Produce recent-form diagnostics with no imputation and no betting score.

    Convention: program form strings are assumed to list the most recent start
    first, as on the supported French program cards. A trend is only emitted
    when at least four numeric finishing positions are available.
    """
    from src.model.race_type import canonical_race_type, race_type_family

    tokens = tokenize_form(value)
    finishes: list[int] = []
    statuses: list[str] = []
    zeros = 0
    unknown: list[str] = []

    for token in tokens:
        match = _FINISH_TOKEN.fullmatch(token)
        if match:
            position = int(match.group(1))
            if position == 0:
                zeros += 1
            elif 1 <= position <= 99:
                finishes.append(position)
            else:
                unknown.append(token)
        elif token in _STATUS_MARKERS:
            statuses.append(token)
        else:
            unknown.append(token)

    count = len(finishes)
    top3 = sum(position <= 3 for position in finishes)
    top5 = sum(position <= 5 for position in finishes)
    wins = sum(position == 1 for position in finishes)
    recent = finishes[:3]
    recent_top3 = sum(position <= 3 for position in recent)
    older = finishes[3:]

    trend = None
    if len(finishes) >= 4 and older:
        # Positive values mean the first, newer results have lower/better
        # finishing positions than the older results in the displayed string.
        trend = round(sum(older) / len(older) - sum(recent) / len(recent), 4)

    canonical = canonical_race_type(race_type)
    family = race_type_family(canonical)

    return {
        "race_type": canonical or "UNKNOWN",
        "discipline_family": family,
        "raw_form": str(value) if value not in (None, "") else None,
        "tokens": tokens,
        "sample_tokens": len(tokens),
        "numeric_finishes": finishes,
        "valid_finish_count": count,
        "wins": wins,
        "top3_finishes": top3,
        "top5_finishes": top5,
        "win_rate_among_numeric_finishes": round(wins / count, 4) if count else None,
        "top3_rate_among_numeric_finishes": round(top3 / count, 4) if count else None,
        "top5_rate_among_numeric_finishes": round(top5 / count, 4) if count else None,
        "mean_numeric_finish": round(sum(finishes) / count, 4) if count else None,
        "recent3_numeric_finishes": recent,
        "recent3_top3_rate": round(recent_top3 / len(recent), 4) if recent else None,
        "recent_vs_older_finish_delta": trend,
        "status_markers": statuses,
        "zero_or_unplaced_markers": zeros,
        "unknown_tokens": unknown,
        "availability": "parsed" if count else ("status_only" if tokens else "missing"),
        "ordering_assumption": "most_recent_first",
        "use_policy": {
            "is_diagnostic_only": True,
            "used_in_model_score": False,
            "status_markers_are_not_assumed_to_share_identical_meaning_across_disciplines": True,
        },
    }
