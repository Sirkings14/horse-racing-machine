import unittest

from src.parsers.program_parser import extract_published_arrival


class PublishedArrivalDateScopeTests(unittest.TestCase):
    def test_ignores_previous_days_arrival_in_program_pdf(self):
        text = "ARRIVEE DU 11 OCTOBRE : 9 - 10 - 4"
        self.assertEqual(extract_published_arrival(text, "2026-10-12"), [])

    def test_accepts_arrival_when_printed_date_matches_program_date(self):
        text = "ARRIVEE DU 12 OCTOBRE : 9 - 10 - 4"
        self.assertEqual(extract_published_arrival(text, "2026-10-12"), [9, 10, 4])

    def test_accepts_accented_arrival_label(self):
        text = "ARRIVÉE DU 12 OCTOBRE : 9 - 10 - 4"
        self.assertEqual(extract_published_arrival(text, "2026-10-12"), [9, 10, 4])

    def test_fails_closed_when_program_date_is_missing_or_invalid(self):
        text = "ARRIVEE DU 12 OCTOBRE : 9 - 10 - 4"
        self.assertEqual(extract_published_arrival(text), [])
        self.assertEqual(extract_published_arrival(text, "not-a-date"), [])

    def test_rejects_duplicate_or_out_of_range_horse_numbers(self):
        self.assertEqual(
            extract_published_arrival("ARRIVEE DU 12 OCTOBRE : 9 - 9 - 4", "2026-10-12"),
            [],
        )
        self.assertEqual(
            extract_published_arrival("ARRIVEE DU 12 OCTOBRE : 9 - 10 - 24", "2026-10-12"),
            [],
        )


if __name__ == "__main__":
    unittest.main()
