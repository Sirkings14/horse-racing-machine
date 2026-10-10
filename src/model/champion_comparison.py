"""Paired chronological champion-vs-candidate comparison for V3 reports.

Predictive approval here is separate from profitability. The economic gate still
requires observed market prices and official payouts for the exact bet type.
"""
from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[2]
CURRENT_REPORT = BASE_DIR / "data" / "model" / "v3_backtest_report.json"
REFERENCE_FILE = BASE_DIR / "data" / "model" / "v3_champion_reference.json"
OUTPUT_FILE = BASE_DIR / "data" / "model" / "champion_comparison_report.json"

MIN_PAIRED_RACES = 1000
MIN_MEAN_TOP5_COVERAGE_LIFT = 0.05
MAX_WINNER_TOP3_REGRESSION = 0.01
MAX_BRIER_REGRESSION = 0.003
MAX_LOG_LOSS_REGRESSION = 0.01
MAX_ECE_REGRESSION = 0.01


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return payload


def _compact_race(row: dict[str, Any]) -> dict[str, Any] | None:
    key = str(row.get("race_key") or "").strip()
    if not key:
        return None
    if row.get("top3_coverage_by_top5") is None or row.get("winner_hit_at_3") is None:
        return None
    return {
        "race_key": key,
        "winner_hit_at_1": bool(row.get("winner_hit_at_1", False)),
        "winner_hit_at_3": bool(row.get("winner_hit_at_3", False)),
        "top3_coverage_by_top3": row.get("top3_coverage_by_top3"),
        "top3_coverage_by_top5": row.get("top3_coverage_by_top5"),
        "field_size": row.get("field_size"),
    }


def preserve_champion_reference(
    source_file: Path = CURRENT_REPORT,
    reference_file: Path = REFERENCE_FILE,
) -> dict[str, Any]:
    """Snapshot compact race-level champion metrics once; never overwrite it."""
    if reference_file.exists():
        existing = _load(reference_file)
        if existing.get("schema_version") != 1 or not existing.get("race_results"):
            raise ValueError("Existing champion reference is malformed; refusing to overwrite it.")
        return {
            "status": "existing_reference_preserved",
            "reference_file": str(reference_file.relative_to(BASE_DIR)),
            "races": len(existing["race_results"]),
        }

    if not source_file.exists():
        raise FileNotFoundError(f"Cannot preserve champion report; missing {source_file}")
    raw = source_file.read_bytes()
    source = json.loads(raw.decode("utf-8"))
    if not isinstance(source, dict) or not isinstance(source.get("race_results"), list):
        raise ValueError("Current stored V3 backtest report has no race_results list.")
    races = [
        compact for row in source["race_results"]
        if isinstance(row, dict)
        for compact in [_compact_race(row)]
        if compact is not None
    ]
    if len(races) < MIN_PAIRED_RACES:
        raise ValueError(
            f"Champion reference has only {len(races)} race rows; "
            f"need at least {MIN_PAIRED_RACES} to establish a reference."
        )
    reference = {
        "schema_version": 1,
        "reference_model": "stored pre-change V3 champion",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_report": str(source_file.relative_to(BASE_DIR)),
        "source_report_sha256": hashlib.sha256(raw).hexdigest(),
        "source_method": source.get("method"),
        "metrics": source.get("metrics") or {},
        "evaluated_races": len(races),
        "race_results": races,
        "policy": {
            "reference_is_frozen_once_created": True,
            "paired_race_keys_required": True,
            "predictive_approval_is_not_profitability_approval": True,
        },
    }
    reference_file.parent.mkdir(parents=True, exist_ok=True)
    reference_file.write_text(json.dumps(reference, indent=2, ensure_ascii=False), encoding="utf-8")
    result = {
        "status": "reference_created",
        "reference_file": str(reference_file.relative_to(BASE_DIR)),
        "races": len(races),
        "source_report_sha256": reference["source_report_sha256"],
    }
    print(json.dumps(result, indent=2))
    return result


def _bootstrap_ci(values: list[float], seed: int = 2718, iterations: int = 2000) -> dict[str, float | None]:
    if not values:
        return {"mean": None, "lower_95": None, "upper_95": None}
    n = len(values)
    mean = sum(values) / n
    rng = random.Random(seed)
    samples = []
    for _ in range(iterations):
        samples.append(sum(values[rng.randrange(n)] for _ in range(n)) / n)
    samples.sort()
    return {
        "mean": round(mean, 6),
        "lower_95": round(samples[int(0.025 * iterations)], 6),
        "upper_95": round(samples[int(0.975 * iterations) - 1], 6),
    }


def compare_reports(
    candidate: dict[str, Any],
    reference: dict[str, Any],
    min_paired_races: int = MIN_PAIRED_RACES,
) -> dict[str, Any]:
    """Compare the model candidate and frozen champion by identical race keys."""
    baseline_by_key = {
        str(row.get("race_key")): row
        for row in reference.get("race_results", [])
        if isinstance(row, dict) and row.get("race_key")
    }
    candidate_by_key = {
        str(row.get("race_key")): row
        for row in candidate.get("race_results", [])
        if isinstance(row, dict) and row.get("race_key")
    }
    common_keys = sorted(set(baseline_by_key) & set(candidate_by_key))
    paired = []
    top5_diffs: list[float] = []
    winner3_diffs: list[float] = []
    top3_diffs: list[float] = []
    for key in common_keys:
        before = baseline_by_key[key]
        after = candidate_by_key[key]
        try:
            before_top5 = float(before["top3_coverage_by_top5"])
            after_top5 = float(after["top3_coverage_by_top5"])
            before_winner3 = float(bool(before["winner_hit_at_3"]))
            after_winner3 = float(bool(after["winner_hit_at_3"]))
            before_top3 = float(before["top3_coverage_by_top3"])
            after_top3 = float(after["top3_coverage_by_top3"])
        except (KeyError, TypeError, ValueError):
            continue
        d_top5 = after_top5 - before_top5
        d_winner3 = after_winner3 - before_winner3
        d_top3 = after_top3 - before_top3
        top5_diffs.append(d_top5)
        winner3_diffs.append(d_winner3)
        top3_diffs.append(d_top3)
        paired.append({
            "race_key": key,
            "champion_top3_covered_by_top5": before_top5,
            "candidate_top3_covered_by_top5": after_top5,
            "top5_coverage_delta": d_top5,
            "champion_winner_in_top3": bool(before_winner3),
            "candidate_winner_in_top3": bool(after_winner3),
            "winner_top3_delta": d_winner3,
        })

    top5_ci = _bootstrap_ci(top5_diffs)
    winner3_ci = _bootstrap_ci(winner3_diffs, seed=2719)
    top3_ci = _bootstrap_ci(top3_diffs, seed=2720)
    n = len(paired)
    reasons: list[str] = []
    if n < min_paired_races:
        reasons.append("insufficient_paired_champion_races")
    if top5_ci["mean"] is None or top5_ci["mean"] < MIN_MEAN_TOP5_COVERAGE_LIFT:
        reasons.append("no_material_top5_coverage_uplift")
    if top5_ci["lower_95"] is None or top5_ci["lower_95"] <= 0.0:
        reasons.append("top5_coverage_uplift_not_confidently_positive")
    if winner3_ci["mean"] is None or winner3_ci["mean"] < -MAX_WINNER_TOP3_REGRESSION:
        reasons.append("winner_in_top3_regression_exceeds_tolerance")

    candidate_metrics = candidate.get("metrics") or {}
    reference_metrics = reference.get("metrics") or {}
    probability_regressions = {}
    for metric, max_delta, reason in (
        ("brier_top3", MAX_BRIER_REGRESSION, "top3_brier_regression_exceeds_tolerance"),
        ("log_loss_top3", MAX_LOG_LOSS_REGRESSION, "top3_log_loss_regression_exceeds_tolerance"),
        ("ece_top3", MAX_ECE_REGRESSION, "top3_calibration_regression_exceeds_tolerance"),
    ):
        try:
            new_value = float(candidate_metrics[metric])
            old_value = float(reference_metrics[metric])
            delta = new_value - old_value
        except (KeyError, TypeError, ValueError):
            probability_regressions[metric] = {"candidate": candidate_metrics.get(metric), "champion": reference_metrics.get(metric), "delta": None}
            reasons.append(f"missing_comparable_metric_{metric}")
            continue
        probability_regressions[metric] = {
            "candidate": round(new_value, 6),
            "champion": round(old_value, 6),
            "delta": round(delta, 6),
            "max_allowed_regression": max_delta,
        }
        if delta > max_delta:
            reasons.append(reason)

    comparison = {
        "schema_version": 1,
        "status": "approved" if not reasons else "rejected",
        "approved": not reasons,
        "reasons": reasons,
        "paired_races": n,
        "candidate_evaluated_races": len(candidate_by_key),
        "champion_evaluated_races": len(baseline_by_key),
        "primary_metric": "actual_top3_runners_covered_by_predicted_top5",
        "top5_coverage_paired_delta": top5_ci,
        "winner_in_top3_paired_delta": winner3_ci,
        "top3_coverage_by_top3_paired_delta": top3_ci,
        "probability_quality_comparison": probability_regressions,
        "acceptance_thresholds": {
            "minimum_paired_races": min_paired_races,
            "minimum_mean_top5_coverage_lift": MIN_MEAN_TOP5_COVERAGE_LIFT,
            "top5_coverage_lower_95_ci_must_exceed": 0.0,
            "maximum_winner_in_top3_regression": MAX_WINNER_TOP3_REGRESSION,
            "maximum_brier_regression": MAX_BRIER_REGRESSION,
            "maximum_log_loss_regression": MAX_LOG_LOSS_REGRESSION,
            "maximum_ece_regression": MAX_ECE_REGRESSION,
        },
        "policy": {
            "paired_on_same_race_keys": True,
            "uses_chronological_walk_forward_reports": True,
            "predictive_approval_is_not_profitability_approval": True,
            "real_money_betting_gate_unchanged": True,
        },
        "paired_race_details": paired,
    }
    return comparison


def main() -> None:
    import sys

    args = set(sys.argv[1:])
    if "--preserve-reference" in args:
        preserve_champion_reference()
        return
    candidate = _load(CURRENT_REPORT)
    if not REFERENCE_FILE.exists():
        raise FileNotFoundError(
            "Champion reference is missing. Run with --preserve-reference before overwriting the current report."
        )
    reference = _load(REFERENCE_FILE)
    comparison = compare_reports(candidate, reference)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(comparison, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "status": comparison["status"],
        "approved": comparison["approved"],
        "reasons": comparison["reasons"],
        "paired_races": comparison["paired_races"],
        "primary_delta": comparison["top5_coverage_paired_delta"],
        "probability_quality_comparison": comparison["probability_quality_comparison"],
        "output": str(OUTPUT_FILE.relative_to(BASE_DIR)),
    }, indent=2))


if __name__ == "__main__":
    main()
