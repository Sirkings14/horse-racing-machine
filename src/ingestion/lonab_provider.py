from src.ingestion.lonab_scraper import LonabScraper


class LonabProvider:
    """
    LONAB-specific provider for the race machine.

    Converts data discovered by the scraper into
    categories used by the rest of the machine.
    """

    def __init__(self):

        self.scraper = LonabScraper()

    def get_upcoming_races(self):
        """
        Discover the newest race-program documents.

        Detailed race extraction is added in the
        next processing stage.
        """

        records = (
            self.scraper.discover_race_documents(
                pages=2
            )
        )

        programs = []

        for record in records:

            if record["type"] != "program":
                continue

            programs.append(record)

        return programs

    def get_historical_races(self):
        """
        Discover historical programs and results.
        """

        return (
            self.scraper.discover_race_documents()
        )

    def get_race_program(self, race_id):

        raise NotImplementedError(
            "Race-level program extraction "
            "will be implemented after PDF "
            "parsing is connected."
        )

    def get_race_results(self, race_id):

        raise NotImplementedError(
            "Race-level result extraction "
            "will be implemented after PDF "
            "parsing is connected."
        )
