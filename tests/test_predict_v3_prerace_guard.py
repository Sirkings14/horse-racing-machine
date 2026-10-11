import unittest
from unittest.mock import patch

from src.model import predict_v3


class PreraceProgramSelectionTests(unittest.TestCase):
    def setUp(self):
        self.races = [
            {"race_key": "2026-10-11|AUTEUIL|3", "date": "2026-10-11", "structured_file": "structured/today.json"},
            {"race_key": "2026-10-12|MARSEILLE-BORELY|4", "date": "2026-10-12", "structured_file": "structured/tomorrow.json"},
        ]
        self.programs = {
            "today.json": {"date": "2026-10-11", "published_arrival": [8, 13, 12, 7, 4]},
            "tomorrow.json": {"date": "2026-10-12", "published_arrival": []},
        }

    def _fake_load(self, path):
        return self.programs[path.name]

    def test_skips_same_day_completed_race_and_selects_next_race(self):
        # The future program also contains a result-like line from older material.
        self.programs["tomorrow.json"]["published_arrival"] = [3, 4, 1]
        with patch.object(predict_v3, "_json", side_effect=self._fake_load):
            entry, program = predict_v3._first_unfinished_program(self.races, today_iso="2026-10-11")

        self.assertEqual(entry["race_key"], "2026-10-12|MARSEILLE-BORELY|4")
        self.assertEqual(program["date"], "2026-10-12")

    def test_returns_none_when_every_candidate_has_past_or_same_day_arrival(self):
        self.programs["tomorrow.json"]["date"] = "2026-10-11"
        with patch.object(predict_v3, "_json", side_effect=self._fake_load):
            entry, program = predict_v3._first_unfinished_program(self.races, today_iso="2026-10-11")

        self.assertIsNone(entry)
        self.assertIsNone(program)

    def test_selects_first_race_when_no_arrival_is_published(self):
        self.programs["today.json"]["published_arrival"] = []
        with patch.object(predict_v3, "_json", side_effect=self._fake_load):
            entry, program = predict_v3._first_unfinished_program(self.races, today_iso="2026-10-11")

        self.assertEqual(entry["race_key"], "2026-10-11|AUTEUIL|3")
        self.assertEqual(program["date"], "2026-10-11")


if __name__ == "__main__":
    unittest.main()
