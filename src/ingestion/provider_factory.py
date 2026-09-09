from src.ingestion.lonab_provider import (
    LonabProvider,
)


def get_race_provider():
    """
    The race machine currently uses LONAB
    as its primary data provider.
    """

    return LonabProvider()
