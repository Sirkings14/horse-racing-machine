from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from src.model.feature_engineering import FEATURE_NAMES, build_matrix

BASE_DIR = Path(__file__).resolve().parents[2]
REPORT_FILE = BASE_DIR / "data" / "model" / "feature_drift_report.json"


def _ks_statistic(reference: np.ndarray, current: np.ndarray) -> float:
    reference = np.sort(reference)
    current = np.sort(current)
    if len(reference) == 0 or len(current) == 0:
        return 0.0
    values = np.sort(np.concatenate([reference, current]))
    ref_cdf = np.searchsorted(reference, values, side="right") / len(reference)
    cur_cdf = np.searchsorted(current, values, side="right") / len(current)
    return float(np.max(np.abs(ref_cdf - cur_cdf)))


def _severity(ks: float) -> str:
    if ks >= 0.35:
        return "severe"
    if ks >= 0.20:
        return "moderate"
    if ks >= 0.10:
        return "mild"
    return "stable"


def compare_feature_distributions(
    training_rows: Sequence[dict[str, Any]],
    current_rows: Sequence[dict[str, Any]],
    race_key: str | None = None,
) -> dict[str, Any]:
    reference = build_matrix(training_rows)
    current = build_matrix(current_rows)
    features: dict[str, Any] = {}

    # A live race is too small a sample for a two-sample KS drift diagnosis.
    # Report it as unrated rather than manufacturing a severe alert.
    if len(current) < 30:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "race_key": race_key,
            "status": "insufficient_current_sample",
            "overall_severity": "unrated",
            "reference_rows": int(len(reference)),
            "current_rows": int(len(current)),
            "severe_feature_count": 0,
            "moderate_feature_count": 0,
            "method": "two_sample_kolmogorov_smirnov_on_model_features",
            "policy": {
                "drift_is_observational": True,
                "prediction_not_blocked_by_drift_alone": True,
                "severe_drift_should_trigger_review": True,
            },
            "reason": "Current sample is too small for a reliable KS drift classification.",
            "features": {},
        }

    severe = 0
    moderate = 0

    if len(reference) == 0 or len(current) == 0:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "race_key": race_key,
            "status": "insufficient_data",
            "reference_rows": int(len(reference)),
            "current_rows": int(len(current)),
            "features": {},
        }

    for index, name in enumerate(FEATURE_NAMES):
        ks = _ks_statistic(reference[:, index], current[:, index])
        severity = _severity(ks)
        if severity == "severe":
            severe += 1
        elif severity == "moderate":
            moderate += 1
        features[name] = {
            "ks_statistic": round(ks, 6),
            "severity": severity,
            "reference_mean": round(float(np.mean(reference[:, index])), 6),
            "current_mean": round(float(np.mean(current[:, index])), 6),
            "reference_std": round(float(np.std(reference[:, index])), 6),
            "current_std": round(float(np.std(current[:, index])), 6),
        }

    overall = "stable"
    if severe >= 2:
        overall = "severe"
    elif severe >= 1 or moderate >= 2:
        overall = "moderate"
    elif any(item["severity"] == "mild" for item in features.values()):
        overall = "mild"

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "race_key": race_key,
        "status": "measured",
        "overall_severity": overall,
        "reference_rows": int(len(reference)),
        "current_rows": int(len(current)),
        "severe_feature_count": severe,
        "moderate_feature_count": moderate,
        "method": "two_sample_kolmogorov_smirnov_on_model_features",
        "policy": {
            "drift_is_observational": True,
            "prediction_not_blocked_by_drift_alone": True,
            "severe_drift_should_trigger_review": True,
        },
        "features": features,
    }


def write_report(report: dict[str, Any]) -> None:
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def main(
    training_rows: Sequence[dict[str, Any]] | None = None,
    current_rows: Sequence[dict[str, Any]] | None = None,
    race_key: str | None = None,
) -> dict[str, Any]:
    if training_rows is None:
        dataset = BASE_DIR / "data" / "dataset" / "training_dataset_clean.json"
        try:
            training_rows = json.loads(dataset.read_text(encoding="utf-8"))
        except Exception:
            training_rows = []
    report = compare_feature_distributions(training_rows, current_rows or [], race_key)
    write_report(report)
    print(f"FEATURE DRIFT: {report.get('overall_severity', report.get('status'))}")
    return report


if __name__ == "__main__":
    main()
