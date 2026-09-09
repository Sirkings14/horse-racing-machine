from datetime import datetime, timezone


class RaceDiscovery:
    """
    Finds races that should be processed by the machine.

    The actual provider-specific logic will be added after the race-data
    source is connected.
    """

    def __init__(self, provider=None):
        self.provider = provider

    def discover_upcoming_races(self):
        """
        Returns a list of upcoming races.

        Each race should eventually contain at least:

        race_id
        race_date
        race_time
        track
        country
        race_name
        distance
        race_type
        """

        print("Searching for upcoming races...")

        if self.provider is None:
            print(
                "No race provider connected yet. "
                "Race discovery cannot retrieve live races."
            )
            return []

        try:
            races = self.provider.get_upcoming_races()

            if not races:
                print("No upcoming races found.")
                return []

            print(f"Found {len(races)} upcoming races.")
            return races

        except Exception as error:
            print(f"Race discovery failed: {error}")
            return []

    def get_next_race(self):
        """
        Returns the earliest upcoming race.
        """

        races = self.discover_upcoming_races()

        if not races:
            return None

        def race_time(race):
            value = race.get("race_time")

            if isinstance(value, datetime):
                return value

            return datetime.max.replace(tzinfo=timezone.utc)

        races.sort(key=race_time)

        return races[0]
