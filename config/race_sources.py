import os


class RaceSources:
    """
    External race-data source configuration.

    URLs and API credentials are intentionally loaded from GitHub Secrets
    or environment variables rather than hard-coded.
    """

    # Provider / source name
    PROVIDER_NAME = os.getenv("RACE_PROVIDER_NAME", "")

    # Base URL or API endpoint
    BASE_URL = os.getenv("RACE_PROVIDER_BASE_URL", "")

    # Optional API key
    API_KEY = os.getenv("RACE_PROVIDER_API_KEY", "")

    # Request timeout
    REQUEST_TIMEOUT = 30


race_sources = RaceSources()
