import json
import os
from datetime import datetime

from src.config import (
    RAW_PROGRAMS_DIR,
    RAW_RESULTS_DIR,
    PROCESSED_DATA_DIR
)


def ensure_directories():
    """
    Create all required data directories.
    """

    directories = [
        RAW_PROGRAMS_DIR,
        RAW_RESULTS_DIR,
        PROCESSED_DATA_DIR
    ]

    for directory in directories:
        os.makedirs(directory, exist_ok=True)


def save_program(data, filename=None):
    """
    Save a raw race program.
    """

    ensure_directories()

    if filename is None:
        timestamp = datetime.utcnow().strftime(
            "%Y%m%d_%H%M%S"
        )

        filename = f"program_{timestamp}.json"

    filepath = os.path.join(
        RAW_PROGRAMS_DIR,
        filename
    )

    with open(
        filepath,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=4
        )

    return filepath


def save_result(data, filename=None):
    """
    Save a raw race result.
    """

    ensure_directories()

    if filename is None:
        timestamp = datetime.utcnow().strftime(
            "%Y%m%d_%H%M%S"
        )

        filename = f"result_{timestamp}.json"

    filepath = os.path.join(
        RAW_RESULTS_DIR,
        filename
    )

    with open(
        filepath,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=4
        )

    return filepath


def load_json(filepath):
    """
    Load JSON data.
    """

    with open(
        filepath,
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(file)


def list_programs():
    """
    Return all stored program files.
    """

    ensure_directories()

    files = []

    for filename in os.listdir(
        RAW_PROGRAMS_DIR
    ):

        if filename.endswith(".json"):

            files.append(
                os.path.join(
                    RAW_PROGRAMS_DIR,
                    filename
                )
            )

    return sorted(files)


def list_results():
    """
    Return all stored result files.
    """

    ensure_directories()

    files = []

    for filename in os.listdir(
        RAW_RESULTS_DIR
    ):

        if filename.endswith(".json"):

            files.append(
                os.path.join(
                    RAW_RESULTS_DIR,
                    filename
                )
            )

    return sorted(files)
