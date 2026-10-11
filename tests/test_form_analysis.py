from src.model.form_analysis import analyze_form, tokenize_form


def test_trot_form_reports_numeric_results_and_status_markers_without_imputation():
    result = analyze_form("1.1.5.D.2", "MONTÉ")
    assert result["discipline_family"] == "trot_mounted"
    assert result["numeric_finishes"] == [1, 1, 5, 2]
    assert result["wins"] == 2
    assert result["top3_finishes"] == 3
    assert result["top5_finishes"] == 4
    assert result["status_markers"] == ["D"]
    assert result["recent_vs_older_finish_delta"] is not None
    assert result["use_policy"]["used_in_model_score"] is False


def test_flat_form_with_suffixes_and_status_only_tokens():
    result = analyze_form("1a 2p 3a 0 T", "PLAT")
    assert tokenize_form("1a 2p 3a 0 T") == ["1A", "2P", "3A", "0", "T"]
    assert result["numeric_finishes"] == [1, 2, 3]
    assert result["zero_or_unplaced_markers"] == 1
    assert result["status_markers"] == ["T"]
    assert result["top3_rate_among_numeric_finishes"] == 1.0


def test_missing_and_unrecognized_form_remain_explicit():
    missing = analyze_form(None, "PLAT")
    odd = analyze_form("XYZ.1.2", "PLAT")
    assert missing["availability"] == "missing"
    assert missing["numeric_finishes"] == []
    assert odd["unknown_tokens"] == ["XYZ"]
    assert odd["availability"] == "parsed"

def test_trend_keeps_status_markers_in_their_original_start_window():
    result = analyze_form("1.1.D.2.2", "ATTELE")
    assert result["recent3_numeric_finishes"] == [1, 1]
    assert result["recent3_top3_rate"] == 1.0
    assert result["recent_vs_older_finish_delta"] == 1.0
