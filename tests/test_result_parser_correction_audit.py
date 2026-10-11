import json
from pathlib import Path

from scripts.audit_result_parser_corrections import audit_corpus, compare_arrivals


def test_arrival_change_classification_is_conservative():
    assert compare_arrivals([9, 10, 4, 1], [9, 10, 4]) == "legacy_has_extra_trailing_values"
    assert compare_arrivals([9, 10, 4], [9, 10, 4, 3, 2]) == "reparse_has_more_positions"
    assert compare_arrivals([9, 10, 4], [9, 4, 10]) == "arrival_sequence_changed"
    assert compare_arrivals([9, 10, 4], [9, 10, 4]) == "unchanged"


def test_audit_reports_changes_without_modifying_legacy_json(tmp_path: Path):
    processed = tmp_path / "processed"
    structured = tmp_path / "structured"
    processed.mkdir()
    structured.mkdir()
    text_file = processed / "result_sample.txt"
    legacy_file = structured / "result_sample.json"

    text_file.write_text(
        "DU : 10 - 10 - 2026 - REUNION - 1 - ( CAEN )\n"
        "4ième 9 - 10 - 4 10 1\\u202f400 74 9 - 4 10 700\n",
        encoding="utf-8",
    )
    legacy = {
        "document_type": "result",
        "date": "2026-10-10",
        "meeting": 1,
        "track": "CAEN",
        "races": [{"race_number": 4, "arrival": [9, 10, 4, 1]}],
    }
    legacy_file.write_text(json.dumps(legacy), encoding="utf-8")
    original = legacy_file.read_text(encoding="utf-8")

    report = audit_corpus(processed, structured)
    assert report["races_compared"] == 1
    assert report["changed_races"] == 1
    assert report["legacy_has_extra_trailing_values"] == 1
    assert report["changed_race_samples"][0]["legacy_arrival"] == [9, 10, 4, 1]
    assert report["changed_race_samples"][0]["reparsed_arrival"] == [9, 10, 4]
    assert report["policy"]["rewrites_structured_results"] is False
    assert legacy_file.read_text(encoding="utf-8") == original
