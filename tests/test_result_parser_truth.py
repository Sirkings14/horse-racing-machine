import unittest
from pathlib import Path

from src.parsers.results_parser import extract_arrival_from_line, parse_result_file


class ResultParserTruthTests(unittest.TestCase):
    def test_payout_numbers_are_not_treated_as_horses(self):
        result = extract_arrival_from_line("4e 1 - 4 - 3 - 700 - 64 - 5 - 650 - 2328")
        self.assertIsNotNone(result)
        self.assertEqual(result["race_number"], 4)
        self.assertEqual(result["arrival"], [1, 4, 3])

    def test_normal_arrival_is_preserved(self):
        result = extract_arrival_from_line("1ère 13 - 8 - 10 - 1 - 5")
        self.assertEqual(result["arrival"], [13, 8, 10, 1, 5])

    def test_unaccented_ere_rank_label_is_supported(self):
        result = extract_arrival_from_line("1ere 5 - 3 - 8 5 1,10 5 - 3 3,80")
        self.assertIsNotNone(result)
        self.assertEqual(result["race_number"], 1)
        self.assertEqual(result["arrival"], [5, 3, 8])

    def test_actual_argentan_result_text_with_unaccented_ere_label(self):
        path = Path("data/processed/results/result_ECD_26-05-2024_R4_0_2804affa77_5044acb316.txt")
        if not path.exists():
            self.skipTest("processed result text is omitted by this workflow's sparse checkout")
        payload = parse_result_file(path)
        race = next(item for item in payload["races"] if item["race_number"] == 1)
        self.assertEqual(race["arrival"], [5, 3, 8])


    def test_caen_thousands_separated_payout_does_not_create_horse_1(self):
        line = "4ième 9 - 10 - 4 10 1\\u202f400 74 9 - 4 10 700"
        result = extract_arrival_from_line(line)
        self.assertIsNotNone(result)
        self.assertEqual(result["race_number"], 4)
        self.assertEqual(result["arrival"], [9, 10, 4])

    def test_vincennes_thousands_separated_payout_does_not_replace_fourth_place(self):
        line = "4ième 14 - 6 - 15 6 1\\u202f000 114 14 - 15 6\\u202f650 2110"
        result = extract_arrival_from_line(line)
        self.assertIsNotNone(result)
        self.assertEqual(result["arrival"], [14, 6, 15])


    def test_actual_caen_result_text_does_not_read_payout_digit_as_fourth_horse(self):
        path = Path("data/processed/results/result_ECD_10-10-2026_R1_b166221896_4d03a7985e.txt")
        if not path.exists():
            self.skipTest("processed result text is omitted by this workflow's sparse checkout")
        payload = parse_result_file(path)
        race = next(item for item in payload["races"] if item["race_number"] == 4)
        self.assertEqual(race["arrival"], [9, 10, 4])

    def test_actual_vincennes_result_text_does_not_read_payout_digit_as_fourth_horse(self):
        path = Path("data/processed/results/result_ECD_09-10-2026_R1_31914dd826_3ab2c3af4c.txt")
        if not path.exists():
            self.skipTest("processed result text is omitted by this workflow's sparse checkout")
        payload = parse_result_file(path)
        race = next(item for item in payload["races"] if item["race_number"] == 4)
        self.assertEqual(race["arrival"], [14, 6, 15])

    def test_first_arrival_sequence_stops_before_later_payout_combinations(self):
        line = "1ère 5 - 6 - 9 6 1\\u202f100 3 5 - 6 2\\u202f400 62"
        result = extract_arrival_from_line(line)
        self.assertIsNotNone(result)
        self.assertEqual(result["arrival"], [5, 6, 9])


if __name__ == "__main__":
    unittest.main()
