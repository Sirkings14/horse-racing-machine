import os


# ============================================================
# LONAB HORSE RACING MACHINE
# CENTRAL CONFIGURATION
# ============================================================


# LONAB WEBSITE
LONAB_BASE_URL = "https://www.lonab.bf"


# DATA DIRECTORIES
RAW_PROGRAMS_DIR = "data/raw/programs"
RAW_RESULTS_DIR = "data/raw/results"
PROCESSED_DATA_DIR = "data/processed"


# TELEGRAM
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


# MACHINE SETTINGS
MAX_HISTORICAL_RACES = 1000

TOP_SELECTIONS = 5

MIN_CONFIDENCE_SCORE = 0.50


# REQUEST SETTINGS
REQUEST_TIMEOUT = 30

USER_AGENT = (
    "Mozilla/5.0 "
    "(Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36"
)


HEADERS = {
    "User-Agent": USER_AGENT
}
