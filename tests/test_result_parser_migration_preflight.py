import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.preview_result_parser_migration import preview_migration
from scripts.validate_result_parser_migration_manifest import preflight_manifest


def _make_fixture(root: Path, stale_text: bool = False):
    processed = root / "processed"
    structured = root / "structured"
    processed.mkdir()
    structured.mkdir()
    header = "DU : 10 - 10 - 2026 - REUNION - 1 - ( CAEN )\n"
    text_path = processed / "result_a.txt"
    text_path.write_text(header + "4ième 9 - 10 - 4 10 1 400 74\n", encoding="utf-8")
    json_path = structured / "result_a.json"
    json_path.write_text(json.dumps({
        "document_type": "result", "date": "2026-10-10", "meeting": 1, "track": "CAEN",
        "races": [{"race_number": 4, "arrival": [9, 10, 4, 1]}],
    }), encoding="utf-8")
    index = {
        "2026-10-10|CAEN|4": {
            "horse_numbers": {1, 2, 3, 4, 5, 6, 7, 8, 9, 10},
            "runners_count": 10, "source_file": "program.json", "conflict": False,
        }
    }
    manifest = preview_migration(processed, structured, index)
    if stale_text:
        text_path.write_text(text_path.read_text(encoding="utf-8") + "edited\n", encoding="utf-8")
    return processed, structured, index, manifest


class ResultParserMigrationPreflightTests(unittest.TestCase):
    def test_preflight_accepts_current_preview_but_never_applies_it(self):
        with TemporaryDirectory() as temporary:
            processed, structured, index, manifest = _make_fixture(Path(temporary))
            report = preflight_manifest(manifest, processed, structured, index)
            self.assertEqual(report["status"], "all_current")
            self.assertEqual(report["candidate_groups_seen"], 1)
            self.assertEqual(report["candidate_groups_passed"], 1)
            self.assertEqual(report["candidate_groups_failed"], 0)
            self.assertFalse(report["policy"]["applies_corrections"])
            current = json.loads((structured / "result_a.json").read_text(encoding="utf-8"))
            self.assertEqual(current["races"][0]["arrival"], [9, 10, 4, 1])

    def test_preflight_blocks_manifest_if_source_text_changed(self):
        with TemporaryDirectory() as temporary:
            processed, structured, index, manifest = _make_fixture(Path(temporary), stale_text=True)
            report = preflight_manifest(manifest, processed, structured, index)
            self.assertEqual(report["status"], "stale_or_invalid_candidates_found")
            self.assertEqual(report["candidate_groups_failed"], 1)
            self.assertEqual(
                report["failure_reason_counts"]["one_or_more_copies_are_stale_or_invalid"],
                1,
            )


if __name__ == "__main__":
    unittest.main()
