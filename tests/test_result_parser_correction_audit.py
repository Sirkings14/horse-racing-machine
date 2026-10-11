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

            # Use a true narrow no-break space, matching the PDF extraction.
            payout_space = chr(0x202F)
            text_file.write_text(
                "DU : 10 - 10 - 2026 - REUNION - 1 - ( CAEN )\\n"
                f"4ième 9 - 10 - 4 10 1{payout_space}400 74 9 - 4 10 700\\n",
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
            self.assertEqual(report["races_compared"], 1)
            self.assertEqual(report["changed_races"], 1)
            self.assertEqual(report["legacy_has_extra_trailing_values"], 1)
            self.assertEqual(report["changed_race_samples"][0]["legacy_arrival"], [9, 10, 4, 1])
            self.assertEqual(report["changed_race_samples"][0]["reparsed_arrival"], [9, 10, 4])
            self.assertFalse(report["policy"]["rewrites_structured_results"])
            self.assertEqual(legacy_file.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
