from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable


@dataclass
class HorseHistory:
    starts: int = 0
    wins: int = 0
    top3: int = 0
    top5: int = 0
    finish_sum: float = 0.0
    course_starts: int = 0
    course_top3: int = 0
    distance_starts: int = 0
    distance_top3: int = 0
    recent_finishes: list[int] | None = None

    def __post_init__(self) -> None:
        if self.recent_finishes is None:
            self.recent_finishes = []


def _date_key(row: dict[str, Any]) -> str:
    return str(row.get("date") or "")[:10]


def _horse_key(row: dict[str, Any]) -> str:
    name = str(row.get("horse_name") or row.get("horse") or "").strip().upper()
    return name


def _distance(row: dict[str, Any]) -> int | None:
    try:
        value = int(float(row.get("distance")))
        return value if 800 <= value <= 7000 else None
    except (TypeError, ValueError):
        return None


def _finish(row: dict[str, Any]) -> int | None:
    for key in ("finish_position", "position", "finish"):
        try:
            value = int(row.get(key))
            if value > 0:
                return value
        except (TypeError, ValueError):
            pass
    return None


def _same_distance(a: int | None, b: int | None) -> bool:
    return a is not None and b is not None and abs(a - b) <= 250


def build_walk_forward_profiles(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Create strictly prior-race horse features.

    For each row, profile values are computed from races dated strictly before
    the current race. Rows on the same date are not allowed to teach each other.
    """
    ordered = sorted(
        enumerate(rows),
        key=lambda item: (_date_key(item[1]), str(item[1].get("race_key") or ""), item[0]),
    )
    histories: dict[str, HorseHistory] = defaultdict(HorseHistory)
    output: list[dict[str, Any]] = []
    index = 0

    while index < len(ordered):
        date_key = _date_key(ordered[index][1])
        group_end = index
        while group_end < len(ordered) and _date_key(ordered[group_end][1]) == date_key:
            group_end += 1

        # Build features from history as it existed before this entire date.
        for _, row in ordered[index:group_end]:
            horse_key = _horse_key(row)
            history = histories[horse_key]
            distance = _distance(row)
            starts = history.starts
            recent = history.recent_finishes[-5:] if history.recent_finishes else []
            finish_mean = history.finish_sum / starts if starts else None
            output.append({
                **row,
                "history_starts": starts,
                "history_win_rate": history.wins / starts if starts else 0.0,
                "history_top3_rate": history.top3 / starts if starts else 0.0,
                "history_top5_rate": history.top5 / starts if starts else 0.0,
                "history_avg_finish": finish_mean,
                "history_recent_top3_rate": sum(x <= 3 for x in recent) / len(recent) if recent else 0.0,
                "history_recent_top5_rate": sum(x <= 5 for x in recent) / len(recent) if recent else 0.0,
                "course_starts": history.course_starts,
                "course_top3_rate": history.course_top3 / history.course_starts if history.course_starts else 0.0,
                "distance_starts": history.distance_starts,
                "distance_top3_rate": history.distance_top3 / history.distance_starts if history.distance_starts else 0.0,
            })

        # Only after all features for the date are frozen do we update history.
        for _, row in ordered[index:group_end]:
            horse_key = _horse_key(row)
            if not horse_key:
                continue
            history = histories[horse_key]
            finish = _finish(row)
            if finish is None:
                continue
            distance = _distance(row)
            history.starts += 1
            history.wins += finish == 1
            history.top3 += finish <= 3
            history.top5 += finish <= 5
            history.finish_sum += finish
            if row.get("track"):
                history.course_starts += 1
                history.course_top3 += finish <= 3
            if distance is not None:
                history.distance_starts += 1
                history.distance_top3 += finish <= 3
            history.recent_finishes.append(finish)
            history.recent_finishes = history.recent_finishes[-10:]

        index = group_end

    return output
