"""Stricter selection filters for live play recommendations.

These filters do not change model training. They only decide whether a ranked
prediction is selective enough to be treated as a candidate *bet*. Rankings are
always available for research; PLAY requires evidence gates to clear.
"""
from __future__ import annotations
from typing import Any


def field_size_baseline_win_prob(runners: int) -> float:
    runners = max(2, int(runners or 2))
    return 1.0 / runners


def score_separation(ranked: list[dict[str, Any]]) -> float:
    """Gap between top ensemble score and the median of the rest."""
    if len(ranked) < 2:
        return 0.0
    scores = [float(r.get("ensemble_score") or 0.0) for r in ranked]
    top = scores[0]
    rest = scores[1:]
    median_rest = sorted(rest)[len(rest) // 2]
    return max(0.0, top - median_rest)


def history_coverage(profiled_rows: list[dict[str, Any]]) -> dict[str, float]:
    n = max(1, len(profiled_rows))
    return {
        "history_coverage": sum(1 for r in profiled_rows if int(r.get("history_starts") or 0) > 0) / n,
        "jockey_coverage": sum(1 for r in profiled_rows if int(r.get("jockey_starts") or 0) > 0) / n,
        "trainer_coverage": sum(1 for r in profiled_rows if int(r.get("trainer_starts") or 0) > 0) / n,
        "mean_history_starts": sum(int(r.get("history_starts") or 0) for r in profiled_rows) / n,
    }


def decide_live_play(
    ranked: list[dict[str, Any]],
    profiled_rows: list[dict[str, Any]],
    runners_count: int,
    *,
    min_top_prob: float = 0.18,
    min_separation: float = 0.04,
    min_history_coverage: float = 0.35,
    min_mean_history_starts: float = 1.5,
    min_jockey_coverage: float = 0.20,
    max_field_size: int = 18,
    high_jockey_coverage: float = 0.80,
    relaxed_mean_history_starts: float = 0.8,
) -> dict[str, Any]:
    """Return a conservative play decision for the current race.

    Rankings are always produced by the caller. This gate only decides whether
    the race is selective enough for a PLAY_CANDIDATE bet signal.

    When jockey coverage is high (>= high_jockey_coverage), the mean horse-history
    requirement is relaxed because person-form is the dominant available signal.
    """
    coverage = history_coverage(profiled_rows)
    separation = score_separation(ranked)
    top = ranked[0] if ranked else {}
    top_prob = float(top.get("probability_winner") or 0.0)
    baseline = field_size_baseline_win_prob(runners_count)
    edge_vs_uniform = top_prob - baseline

    effective_min_history = min_mean_history_starts
    history_relaxed = False
    if coverage["jockey_coverage"] >= high_jockey_coverage:
        effective_min_history = min(min_mean_history_starts, relaxed_mean_history_starts)
        history_relaxed = True

    reasons: list[str] = []
    if runners_count > max_field_size:
        reasons.append(f"field_too_large:{runners_count}>{max_field_size}")
    if top_prob < min_top_prob:
        reasons.append(f"top_win_prob_low:{top_prob:.3f}<{min_top_prob}")
    if separation < min_separation:
        reasons.append(f"score_separation_low:{separation:.3f}<{min_separation}")
    if coverage["history_coverage"] < min_history_coverage:
        reasons.append(
            f"history_coverage_low:{coverage['history_coverage']:.2f}<{min_history_coverage}"
        )
    if coverage["mean_history_starts"] < effective_min_history:
        reasons.append(
            f"mean_history_starts_low:{coverage['mean_history_starts']:.2f}<{effective_min_history}"
        )
    if coverage["jockey_coverage"] < min_jockey_coverage:
        reasons.append(
            f"jockey_coverage_low:{coverage['jockey_coverage']:.2f}<{min_jockey_coverage}"
        )
    if edge_vs_uniform < 0.03:
        reasons.append(f"edge_vs_uniform_low:{edge_vs_uniform:.3f}<0.03")

    decision = "NO_BET" if reasons else "PLAY_CANDIDATE"
    recommended = []
    if ranked:
        recommended = [
            int(r["horse_number"])
            for r in ranked[:3]
            if r.get("horse_number") is not None
        ]

    return {
        "decision": decision,
        "gate_reasons": reasons,
        "recommended_numbers": recommended if decision == "PLAY_CANDIDATE" else [],
        "research_numbers": recommended,
        "top_win_probability": round(top_prob, 6),
        "edge_vs_uniform": round(edge_vs_uniform, 6),
        "score_separation": round(separation, 6),
        "coverage": {k: round(v, 4) for k, v in coverage.items()},
        "baseline_win_prob": round(baseline, 6),
        "history_requirement_relaxed": history_relaxed,
        "effective_min_mean_history_starts": effective_min_history,
    }
