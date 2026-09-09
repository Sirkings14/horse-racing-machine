class RaceProvider:
    """
    Base interface for every race-data provider.

    Any provider we connect to must implement these methods.
    """

    def get_upcoming_races(self):
        raise NotImplementedError(
            "The provider must implement get_upcoming_races()."
        )

    def get_race_program(self, race_id):
        raise NotImplementedError(
            "The provider must implement get_race_program()."
        )

    def get_historical_races(self):
        raise NotImplementedError(
            "The provider must implement get_historical_races()."
        )

    def get_race_results(self, race_id):
        raise NotImplementedError(
            "The provider must implement get_race_results()."
        )
