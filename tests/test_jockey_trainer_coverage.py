import json
import tempfile
import unittest
from pathlib import Path

from scripts.audit_jockey_trainer_coverage import audit, race_key


class JockeyTrainerCoverageAuditTests(unittest.TestCase):
    def test_race_key_normalizes_track_and_race_number(self):
        self.assertEqual(race_key("2026-09-11T00:00:00", " Paris-Vincennes ", "4"),
                         "2026-09-11|PARIS-VINCENNES|4")

    def test_audit_counts_fields_and_exact_runner_linkage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            programs_dir = root / "programs"
            programs_dir.mkdir()
            matched_file = root / "matched.json"
            program = {
                "date": "2026-09-11",
                "source_file": "sample.pdf",
                "race": {"track": "TEST TRACK", "race_number": 1, "runners_count": 2},
                "horses": [
                    {"number": 1, "horse": "ONE", "jockey": "J. Rider", "trainer": "T. Trainer"},
                    {"number": 2, "horse": "TWO", "driver": "D. Driver"},
                ],
            }
            (programs_dir / "sample.json").write_text(json.dumps(program), encoding="utf-8")
            matched_file.write_text(json.dumps([{
                "match": {"status": "VERIFIED"},
                "program": program,
                "result": {"date": "2026-09-11", "track": "TEST TRACK",
                           "race_number": 1, "arrival": [2, 1]},
            }]), encoding="utf-8")

            report = audit(programs_dir, matched_file)
            self.assertEqual(report["structured_programs"]["runners"], 2)
            self.assertEqual(report["structured_programs"]["jockey_or_driver_present"], 2)
            self.assertEqual(report["structured_programs"]["trainer_present"], 1)
            self.assertEqual(report["exact_program_to_result_runner_linkage"]
                             ["program_runner_rows_linked_by_race_key_and_number"], 2)
            self.assertEqual(report["verified_matched_records"]["rows_with_horse_number_in_official_arrival"], 2)
            self.assertFalse(report["production_model_changed"])

    def test_explicit_unmatched_status_is_not_overridden_by_program_result_objects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            programs_dir = root / "programs"
            programs_dir.mkdir()
            matched_file = root / "matched.json"
            matched_file.write_text(json.dumps([{
                "match": {"status": "UNMATCHED"},
                "program": {"date": "2026-09-11", "race": {"track": "TEST", "race_number": 1},
                            "horses": [{"number": 1, "jockey": "J. Rider"}]},
                "result": {"date": "2026-09-11", "track": "TEST", "race_number": 1, "arrival": [1]},
            }]), encoding="utf-8")

            report = audit(programs_dir, matched_file)
            self.assertEqual(report["verified_matched_records"]["records_with_program_and_result"], 0)


if __name__ == "__main__":
    unittest.main()
