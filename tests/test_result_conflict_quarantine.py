import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.learning.evaluate_predictions import result_records
from src.learning.result_truth import build_program_runner_index, validate_arrival


class ResultConflictQuarantineTests(unittest.TestCase):
    def test_conflicting_program_rosters_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, numbers in (("a.json", [1, 2, 3]), ("b.json", [1, 2, 4])):
                payload = {
                    "document_type": "program",
                    "date": "2026-10-10",
                    "race": {"track": "AUTEUIL", "race_number": 1},
                    "horses": [{"number": number} for number in numbers],
                }
                (root / name).write_text(json.dumps(payload), encoding="utf-8")
            with patch("src.learning.result_truth.PROGRAMS_DIR", root):
                index = build_program_runner_index()
        key = "2026-10-10|AUTEUIL|1"
        self.assertTrue(index[key]["conflict"])
        truth = validate_arrival(key, [1, 2, 3], index)
        self.assertFalse(truth["accepted_for_learning"])
        self.assertEqual(truth["reason"], "conflicting_program_rosters")

    def test_conflicting_valid_result_documents_quarantine_whole_race(self):
        key = "2026-10-10|AUTEUIL|1"
        program_index = {key: {
            "horse_numbers": {1, 2, 3, 4}, "runners_count": 4,
            "source_file": "program.json", "conflict": False,
        }}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for filename, arrival in (
                ("result_a.json", [1, 2, 3]),
                ("result_b.json", [2, 1, 3]),
            ):
                payload = {
                    "document_type": "result", "date": "2026-10-10",
                    "track": "AUTEUIL",
                    "races": [{"race_number": 1, "arrival": arrival}],
                }
                (root / filename).write_text(json.dumps(payload), encoding="utf-8")
            with patch("src.learning.evaluate_predictions.RESULTS_DIR", root):
                records, audit = result_records(program_index)
        self.assertNotIn(key, records)
        self.assertEqual(audit["conflicting_result_races"], 1)
        self.assertEqual(audit["conflicting_result_documents"], 2)
        self.assertEqual(audit["accepted"], 0)
        self.assertEqual(audit["rejected"], 2)
        self.assertEqual(audit["rejection_reasons"]["conflicting_result_arrivals"], 2)

    def test_invalid_arrival_value_is_not_silently_ignored(self):
        key = "2026-10-10|AUTEUIL|1"
        program_index = {key: {
            "horse_numbers": {1, 2, 3, 4}, "runners_count": 4,
            "source_file": "program.json", "conflict": False,
        }}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = {
                "document_type": "result", "date": "2026-10-10",
                "track": "AUTEUIL",
                "races": [{"race_number": 1, "arrival": [1, 2, "OCR?", 3]}],
            }
            (root / "result.json").write_text(json.dumps(payload), encoding="utf-8")
            with patch("src.learning.evaluate_predictions.RESULTS_DIR", root):
                records, audit = result_records(program_index)
        self.assertNotIn(key, records)
        self.assertEqual(audit["rejection_reasons"]["invalid_arrival_values"], 1)
        self.assertEqual(audit["rejected"], 1)


if __name__ == "__main__":
    unittest.main()
