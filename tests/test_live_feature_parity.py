import unittest
from src.model.predict_v3 import _live_rows

class LiveFeatureParityTests(unittest.TestCase):
    def test_live_rows_preserve_pre_race_horse_fields(self):
        program = {
            "date": "2026-10-08",
            "race": {
                "track": "SAINT-CLOUD",
                "race_number": 1,
                "race_name": "PRIX DE VERSAILLES",
                "race_type": "MONTE",
                "distance": 2000,
                "runners_count": 2,
                "prize_euros": 52800,
            },
            "horses": [
                {"number": 1, "horse": "A", "weight": 60, "draw": 4, "jockey": "J"},
                {"number": 2, "horse": "B", "weight": 58, "draw": 9, "jockey": "K"},
            ],
        }
        rows = _live_rows(program)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["prize_euros"], 52800)
        self.assertEqual(rows[0]["weight"], 60)
        self.assertEqual(rows[0]["draw"], 4)
        self.assertEqual(rows[0]["jockey"], "J")
        self.assertEqual(rows[1]["weight"], 58)
        self.assertEqual(rows[1]["draw"], 9)

if __name__ == "__main__":
    unittest.main()
