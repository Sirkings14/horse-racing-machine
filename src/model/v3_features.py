from __future__ import annotations

import re
from typing import Any, Sequence

import numpy as np

from src.model.truth_gate import prerace_only

FEATURE_NAMES = [
    "history_starts",
    "history_win_rate",
    "history_top3_rate",
    "history_top5_rate",
    "history_recent_top3_rate",
    "history_recent_top5_rate",
    "course_starts",
    "course_top3_rate",
    "distance_starts",
    "distance_top3_rate",
    "history_avg_finish_norm",
    "days_since_last_run_norm",
    "distance_norm",
    "field_size_norm",
    "weight_norm",
    "draw_norm",
    "course_text_signal",
    "distance_text_signal",
    "class_text_signal",
    "jockey_choice_signal",
    "data_completeness",
]


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _first_number(text: str, patterns: Sequence[str]) -> float | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            try:
                return float(match.group(1).replace(",", "."))
            except (TypeError, ValueError):
                continue
    return None


def _text_signals(description: str) -> tuple[float, float, float, float]:
    text = prerace_only(description).lower()
    course = 0.0
    distance = 0.0
    class_signal = 0.0
    jockey_choice = 0.0

    if re.search(r"sur ce parcours|sur le parcours|à longchamp|a longchamp|sur ce tracé|sur ce trace", text):
        course = 1.0
    if re.search(r"distance|m[êe]me distance|sur 1 ?[0-9]{3,4} m|sur 2 ?[0-9]{3,4} m", text):
        distance = 0.5
    if re.search(r"quint[ée]|listed|groupe [1-3]|g[123]", text):
        class_signal = 0.5
    if re.search(r"100 ?%|excellent|très bon|tres bon|réussite|reussite", text):
        class_signal += 0.25
    if re.search(r"avait le choix|a choisi|choix des montes|choix de monte", text):
        jockey_choice = 1.0
    return course, min(distance, 1.0), min(class_signal, 1.0), jockey_choice


def row_to_v3_features(row: dict[str, Any]) -> list[float]:
    description = str(row.get("horse_description") or row.get("description") or "")
    course_text, distance_text, class_text, jockey_choice = _text_signals(description)

    distance = _float(row.get("distance"))
    runners = _float(row.get("runners_count"))
    weight = _float(row.get("weight") if row.get("weight") is not None else row.get("carried_weight"))
    draw = _float(row.get("draw") if row.get("draw") is not None else row.get("stall"))

    avg_finish = row.get("history_avg_finish")
    avg_finish_norm = 0.0 if avg_finish is None else max(0.0, min(1.0, 1.0 - (_float(avg_finish) - 1.0) / 19.0))

    days = _float(row.get("days_since_last_run"))
    days_norm = 0.0 if days <= 0 else max(0.0, min(1.0, 1.0 - abs(days - 21.0) / 60.0))

    values = [
        min(_float(row.get("history_starts")) / 20.0, 1.0),
        max(0.0, min(1.0, _float(row.get("history_win_rate")))),
        max(0.0, min(1.0, _float(row.get("history_top3_rate")))),
        max(0.0, min(1.0, _float(row.get("history_top5_rate")))),
        max(0.0, min(1.0, _float(row.get("history_recent_top3_rate")))),
        max(0.0, min(1.0, _float(row.get("history_recent_top5_rate")))),
        min(_float(row.get("course_starts")) / 10.0, 1.0),
        max(0.0, min(1.0, _float(row.get("course_top3_rate")))),
        min(_float(row.get("distance_starts")) / 10.0, 1.0),
        max(0.0, min(1.0, _float(row.get("distance_top3_rate")))),
        avg_finish_norm,
        days_norm,
        min(distance / 3500.0, 1.0),
        min(runners / 20.0, 1.0),
        min(max(weight / 80.0, 0.0), 1.0),
        min(max(draw / max(runners, 1.0), 0.0), 1.0),
        course_text,
        distance_text,
        class_text,
        jockey_choice,
        1.0 if description.strip() else 0.0,
    ]
    return values


def build_v3_matrix(rows: Sequence[dict[str, Any]]) -> np.ndarray:
    if not rows:
        return np.empty((0, len(FEATURE_NAMES)), dtype=float)
    return np.asarray([row_to_v3_features(row) for row in rows], dtype=float)
