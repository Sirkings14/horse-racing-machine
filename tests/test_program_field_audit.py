from src.dataset.program_field_audit import _counts


def test_counts_detect_source_markers_without_promoting_features():
    text = """
    H.7 H.8 H.6
    2.3.1.D.4 1.2.3.4.5 0.1.A.2.3
    POIDS CORDE DRIVERS ENTRAINEURS PROPRIETAIRES
    8/1 12/1 5/1
    """
    out = _counts(text, 3)
    assert out["sex_age_exact"] is True
    assert out["performance_exact_or_more"] is True
    assert out["weight_marker"] is True
    assert out["draw_marker"] is True
    assert out["driver_marker"] is True
    assert out["trainer_marker"] is True
    assert out["owner_marker"] is True
