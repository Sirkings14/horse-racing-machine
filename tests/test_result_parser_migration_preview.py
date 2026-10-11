import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.preview_result_parser_migration import (
    preview_migration,
    validate_preview_copy_snapshot,
    validate_preview_group_snapshot,
)


def _fixture(root: Path, name: str, arrival_line: str, legacy_arrival: list[int]) -> tuple[Path, Path]:
    processed = root / "processed"
    structured = root / "structured"
    processed.mkdir(exist_ok=True)
    structured.mkdir(exist_ok=True)
    text_path = processed / f"{name}.txt"
    json_path = structured / f"{name}.json"
    text_path.write_text(
        "DU : 10 - 10 - 2026 - REUNION - 1 - ( CAEN )\n"
        + arrival_line + "\n",
        encoding="utf-8",
    )
    json_path.write_text(json.dumps({
        "document_type": "result",
        "date": "2026-10-10",
        "meeting": 1,
        "track": "CAEN",
        "races": [{
            "race_number": 4,
            "arrival": legacy_arrival,
            "winner": legacy_arrival[0] if legacy_arrival else None,
        }],
    }), encoding="utf-8")
    return text_path, json_path


class ResultParserMigrationPreviewTests(unittest.TestCase):
    def test_preview_only_includes_roster_checked_tail_trims_and_never_writes_sources(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            text_path, source = _fixture(root, "result_a", "4ième 9 - 10 - 4 10 1 400 74", [9, 10, 4, 1])
            original = source.read_text(encoding="utf-8")
            index = {
                "2026-10-10|CAEN|4": {
                    "horse_numbers": {1, 2, 3, 4, 5, 6, 7, 8, 9, 10},
                    "runners_count": 10,
                    "source_file": "program.json",
                    "conflict": False,
                }
            }
            report = preview_migration(root / "processed", root / "structured", index)
            self.assertEqual(report["migration_preview_eligible_groups"], 1)
            self.assertEqual(report["eligible_groups"][0]["proposed_arrival"], [9, 10, 4])
            self.assertFalse(report["policy"]["modifies_structured_results"])
            self.assertEqual(report["schema_version"], 2)
            self.assertTrue(report["policy"]["each_candidate_records_input_sha256"])
            copy = report["eligible_groups"][0]["structured_result_copies"][0]
            self.assertEqual(copy["structured_sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertEqual(copy["processed_text_sha256"], hashlib.sha256(text_path.read_bytes()).hexdigest())
            self.assertEqual(len(copy["roster_evidence_sha256"]), 64)
            self.assertEqual(source.read_text(encoding="utf-8"), original)

    def test_conflicting_result_copies_are_not_eligible(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, first = _fixture(root, "result_a", "4ième 9 - 10 - 4 10 1 400 74", [9, 10, 4, 1])
            _, second = _fixture(root, "result_b", "4ième 9 - 10 - 3 10 1 400 74", [9, 10, 3, 1])
            index = {
                "2026-10-10|CAEN|4": {
                    "horse_numbers": {1, 2, 3, 4, 5, 6, 7, 8, 9, 10},
                    "runners_count": 10,
                    "source_file": "program.json",
                    "conflict": False,
                }
            }
            report = preview_migration(root / "processed", root / "structured", index)
            self.assertEqual(report["migration_preview_eligible_groups"], 0)
            self.assertEqual(report["blocked_reason_counts"].get("copies_disagree_after_reparse"), 1)



    def test_snapshot_preflight_accepts_unchanged_inputs_without_applying(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            text_path, source = _fixture(root, "result_a", "4ième 9 - 10 - 4 10 1 400 74", [9, 10, 4, 1])
            index = {
                "2026-10-10|CAEN|4": {
                    "horse_numbers": {1, 2, 3, 4, 5, 6, 7, 8, 9, 10},
                    "runners_count": 10,
                    "source_file": "program.json",
                    "conflict": False,
                }
            }
            report = preview_migration(root / "processed", root / "structured", index)
            group = report["eligible_groups"][0]
            check = validate_preview_group_snapshot(
                group, root / "processed", root / "structured", index
            )
            self.assertTrue(check["valid"])
            self.assertEqual(check["checked_copies"], 1)
            self.assertFalse(check["policy"]["applies_correction"])
            self.assertEqual(json.loads(source.read_text(encoding="utf-8"))["races"][0]["arrival"], [9, 10, 4, 1])

    def test_snapshot_preflight_rejects_modified_processed_text(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            text_path, source = _fixture(root, "result_a", "4ième 9 - 10 - 4 10 1 400 74", [9, 10, 4, 1])
            index = {
                "2026-10-10|CAEN|4": {
                    "horse_numbers": {1, 2, 3, 4, 5, 6, 7, 8, 9, 10},
                    "runners_count": 10,
                    "source_file": "program.json",
                    "conflict": False,
                }
            }
            report = preview_migration(root / "processed", root / "structured", index)
            copy = report["eligible_groups"][0]["structured_result_copies"][0]
            text_path.write_text(text_path.read_text(encoding="utf-8") + "edited\\n", encoding="utf-8")
            check = validate_preview_copy_snapshot(
                copy, root / "processed", root / "structured", index
            )
            self.assertFalse(check["valid"])
            self.assertEqual(check["reason"], "processed_text_sha256_mismatch")

    def test_snapshot_preflight_rejects_changed_roster_evidence(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, source = _fixture(root, "result_a", "4ième 9 - 10 - 4 10 1 400 74", [9, 10, 4, 1])
            index = {
                "2026-10-10|CAEN|4": {
                    "horse_numbers": {1, 2, 3, 4, 5, 6, 7, 8, 9, 10},
                    "runners_count": 10,
                    "source_file": "program.json",
                    "conflict": False,
                }
            }
            report = preview_migration(root / "processed", root / "structured", index)
            copy = report["eligible_groups"][0]["structured_result_copies"][0]
            changed_index = {
                "2026-10-10|CAEN|4": {
                    "horse_numbers": {1, 2, 3, 4, 5, 6, 7, 8, 9, 11},
                    "runners_count": 10,
                    "source_file": "program.json",
                    "conflict": False,
                }
            }
            check = validate_preview_copy_snapshot(
                copy, root / "processed", root / "structured", changed_index
            )
            self.assertFalse(check["valid"])
            self.assertEqual(check["reason"], "roster_evidence_sha256_mismatch")

if __name__ == "__main__":
    unittest.main()
