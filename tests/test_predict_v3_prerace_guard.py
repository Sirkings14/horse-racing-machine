import unittest
from unittest.mock import patch

from src.model import predict_v3


class PreraceProgramSelectionTests(unittest.TestCase):
    def setUp(self):
        self.races = [
            {"race_key": "2026-10-11|AUTEUIL|3", "structured_file": "structured/today.json"},
            {"race_key": "2026-10-12|MARSEILLE-BORELY|4", "structured_file": "structured/tomorrow.json"},
        ]
        self.programs = {
            "today.json": {"date": "2026-10-11", "published_arrival": [8, 13, 12, 7, 4]},
            "tomorrow.json": {"date": "2026-10-12", "published_arrival": []},
        }

    def _fake_load(self, path):
        return self.programs[path.name]

    def test_skips_race_with_published_arrival_and_selects_next_race(self):
        with patch.object(predict_v3, "_json", side_effect=self._fake_load):
            entry, program = predict_v3._first_unfinished_program(self.races)

        self.assertEqual(entry["race_key"], "2026-10-12|MARSEILLE-BORELY|4")
        self.assertEqual(program["date"], "2026-10-12")

    def test_returns_none_when_every_candidate_has_published_arrival(self):
        self.programs["tomorrow.json"]["published_arrival"] = [3, 4, 1]
        with patch.object(predict_v3, "_json", side_effect=self._fake_load):
            entry, program = predict_v3._first_unfinished_program(self.races)

        self.assertIsNone(entry)
        self.assertIsNone(program)

    def test_selects_first_race_when_no_arrival_is_published(self):
        self.programs["today.json"]["published_arrival"] = []
        with patch.object(predict_v3, "_json", side_effect=self._fake_load):
            entry, program = predict_v3._first_unfinished_program(self.races)

        self.assertEqual(entry["race_key"], "2026-10-11|AUTEUIL|3")
        self.assertEqual(program["date"], "2026-10-11")


if __name__ == "__main__":
    unittest.main()
