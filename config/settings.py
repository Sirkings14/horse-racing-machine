import os


class Settings:
    """
    Central configuration for the race machine.
    Secrets are loaded from GitHub Actions Secrets.
    """

    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

    # Data locations
    HISTORICAL_DATA_DIR = "data/raw/historical"
    UPCOMING_DATA_DIR = "data/raw/upcoming"
    PROCESSED_DATA_DIR = "data/processed"
    RESULTS_DATA_DIR = "data/results"

    # Machine behavior
    MAX_RECENT_RACES = 5
    MIN_HISTORICAL_RACES = 3

    # Prediction output
    TOP_SELECTIONS = 5

    # Safety: don't send empty reports
    MIN_RUNNERS_REQUIRED = 2


settings = Settings()
