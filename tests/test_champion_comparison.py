from src.model.champion_comparison import compare_reports


def _report(races, coverage=2.0, winner_top3=0.50, brier=0.20, log_loss=0.60, ece=0.05):
    rows = []
    for i in range(races):
        rows.append({
            "race_key": f"2025-01-{(i % 28) + 1:02d}|TRACK|{i}",
            "winner_hit_at_1": False,
            "winner_hit_at_3": bool(i % 2 == 0) if winner_top3 == 0.50 else i < int(races * winner_top3),
            "top3_coverage_by_top3": 1,
            "top3_coverage_by_top5": coverage,
            "field_size": 12,
        })
    return {
        "metrics": {
            "brier_top3": brier,
            "log_loss_top3": log_loss,
            "ece_top3": ece,
        },
        "race_results": rows,
    }


def test_candidate_is_approved_only_with_material_paired_top5_uplift():
    reference = _report(1000, coverage=2.0)
    candidate = _report(1000, coverage=2.10)
    result = compare_reports(candidate, reference)
    assert result["paired_races"] == 1000
    assert result["approved"] is True
    assert result["top5_coverage_paired_delta"]["mean"] >= 0.05
    assert result["top5_coverage_paired_delta"]["lower_95"] > 0.0


def test_small_top5_uplift_does_not_promote_candidate():
    reference = _report(1000, coverage=2.0)
    candidate = _report(1000, coverage=2.02)
    result = compare_reports(candidate, reference)
    assert result["approved"] is False
    assert "no_material_top5_coverage_uplift" in result["reasons"]


def test_top5_gain_cannot_hide_material_winner_top3_regression():
    reference = _report(1000, coverage=2.0, winner_top3=0.50)
    candidate = _report(1000, coverage=2.20, winner_top3=0.47)
    result = compare_reports(candidate, reference)
    assert result["approved"] is False
    assert "winner_in_top3_regression_exceeds_tolerance" in result["reasons"]


def test_calibration_regression_blocks_challenger():
    reference = _report(1000, coverage=2.0, brier=0.20, log_loss=0.60, ece=0.05)
    candidate = _report(1000, coverage=2.2, brier=0.205, log_loss=0.615, ece=0.066)
    result = compare_reports(candidate, reference)
    assert result["approved"] is False
    assert "top3_brier_regression_exceeds_tolerance" in result["reasons"]
    assert "top3_log_loss_regression_exceeds_tolerance" in result["reasons"]
    assert "top3_calibration_regression_exceeds_tolerance" in result["reasons"]


def test_comparison_requires_sufficient_paired_race_keys():
    reference = _report(100)
    candidate = _report(100, coverage=2.2)
    result = compare_reports(candidate, reference)
    assert result["approved"] is False
    assert "insufficient_paired_champion_races" in result["reasons"]
