from src.model.race_strategy import build_race_strategy


def test_strategy_selects_mounted_trot_checks_and_reports_input_gaps():
    rows = [
        {
            "horse_number": 1, "performance": "1.2.D.3.4", "listed_chrono": "1.12.3",
            "gains": 100000, "jockey": "RIDER", "trainer": "TRAINER",
            "history_starts": 8, "course_starts": 2, "distance_starts": 5,
        },
        {
            "horse_number": 2, "performance": "2.3.1.4.5", "listed_chrono": "1.13.0",
            "gains": 80000, "jockey": "RIDER B", "trainer": "TRAINER B",
            "history_starts": 3, "course_starts": 0, "distance_starts": 1,
        },
    ]
    plan = build_race_strategy("MONTÉ", rows)

    assert plan["canonical_race_type"] == "MONTE"
    assert plan["family"] == "trot_mounted"
    assert plan["model_policy"]["discipline_specific_model"] is False
    assert any("mounted-trot" in item.lower() for item in plan["checks"])
    assert "start_method" in [item["field"] for item in plan["critical_data_gaps"]]
    assert plan["prior_history_coverage"]["history_starts"] == 1.0
    assert plan["model_policy"]["checklist_overrides_betting_guard"] is False


def test_strategy_keeps_unknown_type_on_generic_fallback():
    plan = build_race_strategy("experimental discipline", [{"performance": "1.2.3"}])
    assert plan["family"] == "unknown"
    assert plan["model_policy"]["unknown_type_uses_specialist_rules"] is False
    assert any("not identified" in item.lower() for item in plan["checks"])
