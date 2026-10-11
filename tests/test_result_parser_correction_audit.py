import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.audit_result_parser_corrections import audit_corpus, compare_arrivals


class ResultParserCorrectionAuditTests(unittest.TestCase):
    def test_arrival_change_classification_is_conservative(self):
        self.assertEqual(compare_arrivals([9, 10, 4, 1], [9, 10, 4]), "legacy_has_extra_trailing_values")
        self.assertEqual(compare_arrivals([9, 10, 4], [9, 10, 4, 3, 2]), "reparse_has_more_positions")
        self.assertEqual(compare_arrivals([9, 10, 4], [9, 4, 10]), "arrival_sequence_changed")
        self.assertEqual(compare_arrivals([9, 10, 4], [9, 10, 4]), "unchanged")

    def test_audit_reports_changes_without_modifying_legacy_json(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            processed = root / "processed"
            structured = root / "structured"
            processed.mkdir()
            structured.mkdir()
            text_file = processed / "result_sample.txt"
            legacy_file = structured / "result_sample.json"

            payout_space = chr(0x202F)
            text_file.write_text(
                "DU : 10 - 10 - 2026 - REUNION - 1 - ( CAEN )\\n"
                f"4ième 9 - 10 - 4 10 1{payout_space}400 74 9 - 4 10 700\\n"
                f"8ième 3 1{payout_space}400 5 8 - 5 9{payout_space}200 93\\n",
                encoding="utf-8",
            )
            legacy = {
                "document_type": "result",
                "date": "2026-10-10",
                "meeting": 1,
                "track": "CAEN",
                "races": [
                    {"race_number": 4, "arrival": [9, 10, 4, 1]},
                    {"race_number": 8, "arrival": [3, 1]},
                ],
            }
            legacy_file.write_text(json.dumps(legacy), encoding="utf-8")
            original = legacy_file.read_text(encoding="utf-8")

            approved_index = {
                "2026-10-10|CAEN|4": {
                    "horse_numbers": {1, 2, 3, 4, 5, 6, 7, 8, 9, 10},
                    "runners_count": 10,
                    "source_file": "test_program.json",
                    "conflict": False,
                }
            }
            report = audit_corpus(processed, structured, program_index=approved_index)
            self.assertEqual(report["races_compared"], 1)
            self.assertEqual(report["changed_races"], 1)
            self.assertEqual(report["legacy_has_extra_trailing_values"], 1)
            self.assertEqual(report["changed_race_samples"][0]["legacy_arrival"], [9, 10, 4, 1])
            self.assertEqual(report["changed_race_samples"][0]["reparsed_arrival"], [9, 10, 4])
            self.assertEqual(report["legacy_only_races"], 1)
            legacy_only = report["legacy_only_race_samples"][0]
            self.assertTrue(legacy_only["manual_review_required"])
            self.assertEqual(legacy_only["race_number"], 8)
            self.assertGreaterEqual(len(legacy_only["source_line_evidence"]), 1)
            self.assertIn("8ième 3 1", legacy_only["source_line_evidence"][0]["raw_line"])
            evidence_reasons = {item["review_reason"] for item in legacy_only["source_line_evidence"]}
            expected_reason = (
                next(iter(evidence_reasons))
                if len(evidence_reasons) == 1
                else "multiple_source_line_patterns"
            )
            self.assertEqual(legacy_only["manual_review_reason"], expected_reason)
            self.assertFalse(report["policy"]["rewrites_structured_results"])
            self.assertEqual(report["candidate_races_checked_against_roster"], 1)
            self.assertEqual(report["roster_valid_correction_candidates"], 1)
            self.assertTrue(report["changed_race_samples"][0]["migration_candidate"])
            self.assertEqual(legacy_file.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
