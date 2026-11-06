from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
import re
import unicodedata
from typing import Any, Iterable


@dataclass
class EntityHistory:
    starts: int = 0
    wins: int = 0
    top3: int = 0
    top5: int = 0
    finish_sum: float = 0.0
    recent_finishes: list[int] = field(default_factory=list)
    rated_starts: int = 0
    last_date: date | None = None
    course_stats: dict[str, list[int]] = field(default_factory=dict)
    distance_stats: dict[int, list[int]] = field(default_factory=dict)


def _date_value(row: dict[str, Any]) -> date | None:
    try:
        return date.fromisoformat(str(row.get("date") or "")[:10])
    except ValueError:
        return None


def _date_key(row):
    return str(row.get("date") or "")[:10]


_ID_FIELDS = (
    "horse_id", "horseId", "horse_uid", "horseUid",
    "idCheval", "id_cheval", "identifiantCheval", "identifiant_cheval",
)


def _clean_name(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.upper().replace("\u2019", "'").replace("\u2013", "-").replace("\u2014", "-")
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _horse_key(row: dict[str, Any]) -> str:
    for field_name in _ID_FIELDS:
        value = row.get(field_name)
        if value not in (None, ""):
            return "ID:" + str(value).strip()
    name = _clean_name(row.get("horse_name") or row.get("horse"))
    return "NAME:" + name if name else ""


def _person_key(value: Any) -> str:
    name = _clean_name(value)
    return name if name else ""


def horse_identity_source(row: dict[str, Any]) -> str:
    return "stable_id" if any(row.get(k) not in (None, "") for k in _ID_FIELDS) else "normalized_name"


def _distance(row):
    try:
        value = int(float(row.get("distance")))
        return value if 800 <= value <= 7000 else None
    except (TypeError, ValueError):
        return None


def _finish(row):
    for key in ("finish_position", "position", "finish"):
        try:
            value = int(row.get(key))
            if value > 0:
                return value
        except (TypeError, ValueError):
            pass
    return None


def _bucket(distance: int | None) -> int | None:
    return None if distance is None else int(round(distance / 100.0) * 100)


def _stats(history: EntityHistory, track: str | None, distance: int | None):
    course = history.course_stats.get(str(track or "").upper(), [0, 0, 0, 0])
    ds = dt = dt5 = drated = 0
    if distance is not None:
        center = _bucket(distance)
        for delta in (-200, -100, 0, 100, 200):
            stats = history.distance_stats.get(center + delta)
            if stats:
                starts, top3, top5, rated = stats
                ds += starts
                dt += top3
                dt5 += top5
                drated += rated
    return course, ds, dt, dt5, drated


def _entity_rates(history: EntityHistory) -> dict[str, float | int | None]:
    rated = history.rated_starts
    recent = history.recent_finishes[-5:]
    return {
        "starts": history.starts,
        "win_rate": history.wins / rated if rated else 0.0,
        "top3_rate": history.top3 / rated if rated else 0.0,
        "top5_rate": history.top5 / rated if rated else 0.0,
        "avg_finish": history.finish_sum / rated if rated else None,
        "recent_top3_rate": sum(x <= 3 for x in recent) / len(recent) if recent else 0.0,
        "recent_top5_rate": sum(x <= 5 for x in recent) / len(recent) if recent else 0.0,
        "recent_avg_finish": (sum(recent) / len(recent)) if recent else None,
        "rated_starts": rated,
    }


def _update_entity(history: EntityHistory, finish: int | None, track: str | None, distance: int | None, d: date | None):
    history.starts += 1
    if finish is not None:
        history.rated_starts += 1
        history.wins += finish == 1
        history.top3 += finish <= 3
        history.top5 += finish <= 5
        history.finish_sum += finish
        history.recent_finishes = (history.recent_finishes + [finish])[-10:]
    if d:
        history.last_date = d
    if track:
        s = history.course_stats.setdefault(track, [0, 0, 0, 0])
        s[0] += 1
        if finish is not None:
            s[1] += finish <= 3
            s[2] += finish <= 5
            s[3] += 1
    bucket = _bucket(distance)
    if bucket is not None:
        s = history.distance_stats.setdefault(bucket, [0, 0, 0, 0])
        s[0] += 1
        if finish is not None:
            s[1] += finish <= 3
            s[2] += finish <= 5
            s[3] += 1


def build_walk_forward_profiles(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build only information that existed before each race; same-date races cannot teach one another.

    Extended to include walk-forward jockey and trainer form when those fields
    are present on the rows (they are now carried through from structured programs).
    """
    rows_list = list(rows)
    ordered = list(enumerate(rows_list))
    if any(
        (_date_key(ordered[i][1]), str(ordered[i][1].get("race_key") or ""), ordered[i][0])
        > (_date_key(ordered[i + 1][1]), str(ordered[i + 1][1].get("race_key") or ""), ordered[i + 1][0])
        for i in range(len(ordered) - 1)
    ):
        ordered.sort(key=lambda item: (_date_key(item[1]), str(item[1].get("race_key") or ""), item[0]))

    horse_histories: dict[str, EntityHistory] = defaultdict(EntityHistory)
    jockey_histories: dict[str, EntityHistory] = defaultdict(EntityHistory)
    trainer_histories: dict[str, EntityHistory] = defaultdict(EntityHistory)

    output: list[dict[str, Any]] = []
    index = 0
    while index < len(ordered):
        current_date = _date_key(ordered[index][1])
        end = index
        while end < len(ordered) and _date_key(ordered[end][1]) == current_date:
            end += 1

        for _, row in ordered[index:end]:
            hkey = _horse_key(row)
            jkey = _person_key(row.get("jockey") or row.get("driver"))
            tkey = _person_key(row.get("trainer") or row.get("entraineur"))

            h = horse_histories[hkey]
            j = jockey_histories[jkey] if jkey else EntityHistory()
            t = trainer_histories[tkey] if tkey else EntityHistory()

            course, ds, dt, dt5, drated = _stats(h, row.get("track"), _distance(row))
            hr = _entity_rates(h)
            jr = _entity_rates(j)
            tr = _entity_rates(t)

            days_since = None
            dval = _date_value(row)
            if dval and h.last_date:
                days_since = (dval - h.last_date).days

            output.append({
                **row,
                "horse_identity_source": horse_identity_source(row),
                "history_starts": hr["starts"],
                "history_win_rate": hr["win_rate"],
                "history_top3_rate": hr["top3_rate"],
                "history_top5_rate": hr["top5_rate"],
                "history_avg_finish": hr["avg_finish"],
                "history_recent_top3_rate": hr["recent_top3_rate"],
                "history_recent_top5_rate": hr["recent_top5_rate"],
                "history_recent_avg_finish": hr["recent_avg_finish"],
                "course_starts": course[0],
                "course_top3_rate": course[1] / course[3] if course[3] else 0.0,
                "course_top5_rate": course[2] / course[3] if course[3] else 0.0,
                "distance_starts": ds,
                "distance_top3_rate": dt / drated if drated else 0.0,
                "distance_top5_rate": dt5 / drated if drated else 0.0,
                "days_since_last_run": days_since,
                "jockey_starts": jr["starts"],
                "jockey_win_rate": jr["win_rate"],
                "jockey_top3_rate": jr["top3_rate"],
                "jockey_top5_rate": jr["top5_rate"],
                "jockey_recent_top3_rate": jr["recent_top3_rate"],
                "trainer_starts": tr["starts"],
                "trainer_win_rate": tr["win_rate"],
                "trainer_top3_rate": tr["top3_rate"],
                "trainer_top5_rate": tr["top5_rate"],
                "trainer_recent_top3_rate": tr["recent_top3_rate"],
                "data_completeness": sum(
                    row.get(k) not in (None, "")
                    for k in ("date", "track", "distance", "runners_count", "horse_number", "horse_name")
                ) / 6.0,
            })

        for _, row in ordered[index:end]:
            hkey = _horse_key(row)
            if not hkey:
                continue
            finish = _finish(row)
            track = str(row.get("track") or "").upper()
            distance = _distance(row)
            d = _date_value(row)

            _update_entity(horse_histories[hkey], finish, track, distance, d)

            jkey = _person_key(row.get("jockey") or row.get("driver"))
            if jkey:
                _update_entity(jockey_histories[jkey], finish, track, distance, d)

            tkey = _person_key(row.get("trainer") or row.get("entraineur"))
            if tkey:
                _update_entity(trainer_histories[tkey], finish, track, distance, d)

        index = end
    return output
