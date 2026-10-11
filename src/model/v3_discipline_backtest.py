"""Walk-forward evaluation of per-discipline V3 specialist models.

This is an offline challenger only. Specialists are used only when their
discipline has enough *prior* complete races; all other races use the pooled
model. It does not change the live model or approve betting by itself.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any
import json
import math

from src.dataset.program_history import load_program_history
from src.model.champion_comparison import compare_reports
from src.model.calibration import calibration_metrics
from src.model.historical_profile import build_walk_forward_profiles
from src.model.race_type import canonical_race_type
from src.model.v3_features import tail_complete_races
from src.model.v3_model import fit_v3_model


BASE_DIR = Path(__file__).resolve().parents[2]
DATASET_FILE = BASE_DIR / "data" / "dataset" / "training_dataset_clean.json"
CHAMPION_FILE = BASE_DIR / "data" / "model" / "v3_champion_reference.json"
REPORT_FILE = BASE_DIR / "data" / "model" / "v3_discipline_backtest_report.json"
COMPARISON_FILE = BASE_DIR / "data" / "model" / "discipline_champion_comparison_report.json"

MIN_SPECIALIST_RACES = 300
MIN_SPECIALIST_ROWS = 3000
SPECIALIST_TYPES = {"PLAT", "ATTELE", "MONTE", "HAIES", "STEEPLE-CHASE", "OBSTACLE"}


def discipline_key(value: Any) -> str:
    return canonical_race_type(value) or "UNKNOWN"


def should_train_specialist(race_count: int, row_count: int,
                            min_races: int = MIN_SPECIALIST_RACES,
                            min_rows: int = MIN_SPECIALIST_ROWS) -> bool:
    return race_count >= min_races and row_count >= min_rows


def choose_models(discipline: str, specialist_models: dict[str, dict[str, Any]],
                  pooled_models: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Select a validated discipline-specific model or use the pooled fallback."""
    model = specialist_models.get(discipline)
    if model is not None:
        return model, "discipline_specialist"
    return pooled_models, "pooled_fallback"


def _key(row: dict[str, Any]) -> str:
    return str(row.get("race_key") or "").strip()


def _sort(row: dict[str, Any]) -> tuple[str, str]:
    return str(row.get("date") or "")[:10], _key(row)


def _race_discipline(rows: list[dict[str, Any]]) -> str:
    values = [discipline_key(row.get("race_type")) for row in rows]
    if not values:
        return "UNKNOWN"
    counts: dict[str, int] = defaultdict(int)
    for value in values:
        counts[value] += 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _fit_models(rows: list[dict[str, Any]], epochs: int) -> dict[str, Any]:
    if not rows:
        raise ValueError("Cannot fit a V3 model without rows.")
    return {
        "winner": fit_v3_model(rows, target_field="won", epochs=epochs),
        "top3": fit_v3_model(rows, target_field="top3", epochs=epochs),
        "top5": fit_v3_model(rows, target_field="top5", epochs=epochs),
    }


def _evaluate(ranked: list[dict[str, Any]]) -> dict[str, Any]:
    winner = next((int(row["horse_number"]) for row in ranked if int(row.get("won", 0)) == 1), None)
    actual_top3 = {int(row["horse_number"]) for row in ranked if int(row.get("top3", 0)) == 1}
    predicted_top3 = {int(row["horse_number"]) for row in ranked[:3]}
    predicted_top5 = {int(row["horse_number"]) for row in ranked[:5]}
    field_size = max(len(ranked), 1)
    return {
        "winner_hit_at_1": bool(ranked and winner == int(ranked[0]["horse_number"])),
        "winner_hit_at_3": bool(winner in predicted_top3) if winner is not None else False,
        "top3_coverage_by_top3": len(actual_top3 & predicted_top3),
        "top3_coverage_by_top5": len(actual_top3 & predicted_top5),
        "random_expected_top3_coverage": min(3.0, 3.0 * len(actual_top3) / field_size),
    }


def _bootstrap_mean(values: list[float], seed: int = 781, iterations: int = 1000) -> dict[str, float | None]:
    if not values:
        return {"mean": None, "lower": None, "upper": None}
    import random
    rng = random.Random(seed)
    n = len(values)
    means = [sum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(iterations)]
    means.sort()
    return {
        "mean": round(sum(values) / n, 6),
        "lower": round(means[int(0.025 * iterations)], 6),
        "upper": round(means[int(0.975 * iterations) - 1], 6),
    }


def run(rows: list[dict[str, Any]], min_train_dates: int = 100,
        refit_every_days: int = 365, max_train_rows: int = 25000,
        epochs: int = 20, max_eval_races: int = 3000,
        min_specialist_races: int = MIN_SPECIALIST_RACES,
        min_specialist_rows: int = MIN_SPECIALIST_ROWS) -> dict[str, Any]:
    """Train specialists using prior dates only and score a chronological holdout."""
    rows = [row for row in rows if isinstance(row, dict) and _key(row)]
    history_rows = load_program_history(
        exclude_on_or_after=str(max((row.get("date") or "") for row in rows))[:10]
    ) if rows else []
    profiled = rows if rows and "history_starts" in rows[0] else build_walk_forward_profiles(history_rows + rows)

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in profiled:
        if not row.get("_program_only_history") and _key(row):
            groups[_key(row)].append(row)
    if not groups:
        raise ValueError("No complete race groups available for discipline backtest.")

    keys = sorted(groups, key=lambda key: min(_sort(row) for row in groups[key]))
    date_by_key = {
        key: min(str(row.get("date") or "")[:10] for row in groups[key])
        for key in keys
    }
    discipline_by_key = {key: _race_discipline(groups[key]) for key in keys}
    dates = sorted(set(date_by_key.values()))
    evaluation_keys = set(keys[-max_eval_races:]) if max_eval_races and len(keys) > max_eval_races else set(keys)
    date_to_keys: dict[str, list[str]] = defaultdict(list)
    for key in keys:
        date_to_keys[date_by_key[key]].append(key)

    pooled_models: dict[str, Any] | None = None
    specialist_models: dict[str, dict[str, Any]] = {}
    predictions: list[dict[str, Any]] = []
    probabilities: list[float] = []
    labels: list[int] = []
    model_coverage: dict[str, dict[str, int]] = defaultdict(lambda: {
        "eligible_training_dates": 0,
        "specialist_used_races": 0,
        "pooled_fallback_races": 0,
        "prior_training_races_last_fit": 0,
        "prior_training_rows_last_fit": 0,
    })

    for date_index, date in enumerate(dates):
        if date_index < min_train_dates:
            continue
        if pooled_models is None or (date_index - min_train_dates) % max(refit_every_days, 1) == 0:
            prior_dates = dates[:date_index]
            prior_keys = [key for prior_date in prior_dates for key in date_to_keys[prior_date]]
            pooled_rows = tail_complete_races(
                [row for key in prior_keys for row in groups[key]], max_train_rows
            )
            try:
                pooled_models = _fit_models(pooled_rows, epochs)
            except ValueError:
                pooled_models = None
                specialist_models = {}
                continue

            specialist_models = {}
            for discipline in sorted(SPECIALIST_TYPES):
                specialist_keys = [key for key in prior_keys if discipline_by_key[key] == discipline]
                discipline_rows = tail_complete_races(
                    [row for key in specialist_keys for row in groups[key]], max_train_rows
                )
                if not should_train_specialist(
                    len(specialist_keys), len(discipline_rows),
                    min_specialist_races, min_specialist_rows
                ):
                    continue
                try:
                    specialist_models[discipline] = _fit_models(discipline_rows, epochs)
                except ValueError:
                    # A specialist with insufficient target diversity is not used.
                    continue
                coverage = model_coverage[discipline]
                coverage["eligible_training_dates"] += 1
                coverage["prior_training_races_last_fit"] = len(specialist_keys)
                coverage["prior_training_rows_last_fit"] = len(discipline_rows)

        if pooled_models is None:
            continue
        for key in date_to_keys[date]:
            if key not in evaluation_keys:
                continue
            test_rows = groups[key]
            discipline = discipline_by_key[key]
            chosen_models, selection_mode = choose_models(discipline, specialist_models, pooled_models)
            if selection_mode == "discipline_specialist":
                model_coverage[discipline]["specialist_used_races"] += 1
            else:
                model_coverage[discipline]["pooled_fallback_races"] += 1

            p1 = chosen_models["winner"].predict_proba(test_rows)
            p3 = chosen_models["top3"].predict_proba(test_rows)
            p5 = chosen_models["top5"].predict_proba(test_rows)
            ensemble = [0.25 * a + 0.50 * b + 0.25 * c for a, b, c in zip(p1, p3, p5)]
            ranked = sorted(
                (dict(row, ensemble_score=float(score), p_winner=float(a),
                      p_top3=float(b), p_top5=float(c), discipline=discipline,
                      selection_mode=selection_mode)
                 for row, a, b, c, score in zip(test_rows, p1, p3, p5, ensemble)),
                key=lambda row: (-row["ensemble_score"], int(row.get("horse_number", 9999)))
            )
            ev = _evaluate(ranked)
            ev["race_key"] = key
            ev["field_size"] = len(ranked)
            ev["discipline"] = discipline
            ev["selection_mode"] = selection_mode
            ev["top5_candidates"] = [{
                "horse_number": int(row["horse_number"]),
                "ensemble_score": float(row["ensemble_score"]),
                "probability_winner": float(row.get("p_winner", 0.0)),
                "probability_top3": float(row.get("p_top3", 0.0)),
                "probability_top5": float(row.get("p_top5", 0.0)),
                "won": int(row.get("won", 0)),
                "discipline": discipline,
                "selection_mode": selection_mode,
                **{field: row.get(field) for field in (
                    "win_odds_decimal", "decimal_odds", "starting_price_decimal",
                    "starting_price", "win_odds", "odds", "press_paris_turf_fractional",
                    "press_paris_turf_decimal", "press_tierce_magazine_fractional",
                    "press_tierce_magazine_decimal", "press_odds_status"
                )}
            } for row in ranked[:5]]
            predictions.append(ev)
            probabilities.extend(float(value) for value in p3)
            labels.extend(int(row.get("top3", 0)) for row in test_rows)

    if not predictions:
        raise ValueError("Discipline-specific walk-forward produced no evaluable races.")

    n = len(predictions)
    winner1 = [float(row["winner_hit_at_1"]) for row in predictions]
    winner3 = [float(row["winner_hit_at_3"]) for row in predictions]
    coverage3 = [float(row["top3_coverage_by_top3"]) for row in predictions]
    coverage5 = [float(row["top3_coverage_by_top5"]) for row in predictions]
    random_coverage = [float(row["random_expected_top3_coverage"]) for row in predictions]
    calibration = calibration_metrics(probabilities, labels)
    prevalence = sum(labels) / len(labels) if labels else 0.0
    brier_baseline = prevalence * (1.0 - prevalence)
    log_loss_baseline = -(
        prevalence * math.log(max(prevalence, 1e-6))
        + (1.0 - prevalence) * math.log(max(1.0 - prevalence, 1e-6))
    )
    by_discipline: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for prediction in predictions:
        by_discipline[prediction["discipline"]].append(prediction)
    discipline_metrics = {}
    for discipline, races in sorted(by_discipline.items()):
        discipline_metrics[discipline] = {
            "races": len(races),
            "specialist_used_races": sum(item["selection_mode"] == "discipline_specialist" for item in races),
            "pooled_fallback_races": sum(item["selection_mode"] == "pooled_fallback" for item in races),
            "winner_hit_rate_at_1": round(sum(item["winner_hit_at_1"] for item in races) / len(races), 4),
            "winner_hit_rate_at_3": round(sum(item["winner_hit_at_3"] for item in races) / len(races), 4),
            "average_actual_top3_covered_by_predicted_top5": round(sum(item["top3_coverage_by_top5"] for item in races) / len(races), 4),
        }

    report = {
        "method": "walk_forward_per_discipline_specialists_with_pooled_fallback",
        "dataset_races": len(keys),
        "evaluated_races": n,
        "press_dependency": False,
        "post_race_feature_policy": "hard_exclusion",
        "specialist_thresholds": {
            "minimum_prior_races": min_specialist_races,
            "minimum_prior_rows": min_specialist_rows,
            "all_specialists_fit_on_prior_dates_only": True,
            "complete_race_groups_only": True,
        },
        "metrics": {
            "winner_hit_rate_at_1": round(sum(winner1) / n, 4),
            "winner_hit_rate_at_3": round(sum(winner3) / n, 4),
            "average_actual_top3_covered_by_predicted_top3": round(sum(coverage3) / n, 4),
            "average_actual_top3_covered_by_predicted_top5": round(sum(coverage5) / n, 4),
            "random_baseline_top3_coverage": round(sum(random_coverage) / n, 4),
            **{f"{name}_top3": value for name, value in calibration.items()},
            "brier_baseline_top3": round(brier_baseline, 6),
            "log_loss_baseline_top3": round(log_loss_baseline, 6),
            "coverage3_lift_vs_random": round((sum(coverage3) / n) / (sum(random_coverage) / n) - 1.0, 4)
            if sum(random_coverage) > 0 else None,
        },
        "confidence_intervals": {
            "winner_hit_rate_at_1": _bootstrap_mean(winner1),
            "winner_hit_rate_at_3": _bootstrap_mean(winner3, seed=782),
            "top3_coverage": _bootstrap_mean(coverage3, seed=783),
            "top5_coverage": _bootstrap_mean(coverage5, seed=784),
        },
        "discipline_metrics": discipline_metrics,
        "specialist_training_coverage": {key: dict(value) for key, value in sorted(model_coverage.items())},
        "race_results": predictions,
    }
    return report


def main() -> None:
    rows = json.loads(DATASET_FILE.read_text(encoding="utf-8"))
    report = run(rows)
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "metrics": report["metrics"],
        "discipline_metrics": report["discipline_metrics"],
        "specialist_training_coverage": report["specialist_training_coverage"],
    }, indent=2, ensure_ascii=False))

    if CHAMPION_FILE.exists():
        reference = json.loads(CHAMPION_FILE.read_text(encoding="utf-8"))
        comparison = compare_reports(report, reference)
    else:
        comparison = {
            "schema_version": 1,
            "status": "rejected",
            "approved": False,
            "reasons": ["champion_reference_missing"],
            "paired_races": 0,
        }
    COMPARISON_FILE.parent.mkdir(parents=True, exist_ok=True)
    COMPARISON_FILE.write_text(json.dumps(comparison, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "champion_comparison": {
            "status": comparison["status"],
            "approved": comparison["approved"],
            "reasons": comparison["reasons"],
            "paired_races": comparison["paired_races"],
            "top5_coverage_paired_delta": comparison["top5_coverage_paired_delta"],
        }
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
