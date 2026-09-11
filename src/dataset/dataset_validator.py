from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple


BASE_DIR = Path(__file__).resolve().parents[2]

DATASET_FILE = BASE_DIR / "data" / "dataset" / "training_dataset.json"

CLEAN_DATASET_FILE = (
    BASE_DIR
    / "data"
    / "dataset"
    / "training_dataset_clean.json"
)

REVIEW_FILE = (
    BASE_DIR
    / "data"
    / "dataset"
    / "dataset_review.json"
)

MIN_HORSES_PER_RACE = 8


def load_dataset() -> List[Dict[str, Any]]:
    if not DATASET_FILE.exists():
        raise FileNotFoundError(
            f"Dataset not found: {DATASET_FILE}"
        )

    with DATASET_FILE.open(
        "r",
        encoding="utf-8",
    ) as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError(
            "training_dataset.json must contain a JSON list."
        )

    return data


def group_by_race(
    rows: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    races: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for row in rows:
        race_key = row.get("race_key")

        if not race_key:
            continue

        races[str(race_key)].append(row)

    return dict(races)


def validate_race(
    race_key: str,
    rows: List[Dict[str, Any]],
) -> Tuple[bool, List[str]]:
    reasons: List[str] = []

    if len(rows) < MIN_HORSES_PER_RACE:
        reasons.append(
            f"only {len(rows)} horse rows; "
            f"minimum is {MIN_HORSES_PER_RACE}"
        )

    tracks = {
        str(row.get("track", "")).strip()
        for row in rows
        if row.get("track")
    }

    if len(tracks) != 1:
        reasons.append(
            "missing or inconsistent track information"
        )

    dates = {
        str(row.get("date", "")).strip()
        for row in rows
        if row.get("date")
    }

    if len(dates) != 1:
        reasons.append(
            "missing or inconsistent date information"
        )

    race_numbers = {
        row.get("race_number")
        for row in rows
        if row.get("race_number") is not None
    }

    if len(race_numbers) != 1:
        reasons.append(
            "missing or inconsistent race number"
        )

    winners = [
        row
        for row in rows
        if row.get("won") == 1
    ]

    if len(winners) != 1:
        reasons.append(
            f"expected exactly 1 winner, found {len(winners)}"
        )

    top3_count = sum(
        1
        for row in rows
        if row.get("top3") == 1
    )

    if top3_count != 3:
        reasons.append(
            f"expected 3 top-3 horses, found {top3_count}"
        )

    horse_numbers = [
        row.get("horse_number")
        for row in rows
        if row.get("horse_number") is not None
    ]

    if len(horse_numbers) != len(set(horse_numbers)):
        reasons.append(
            "duplicate horse numbers found"
        )

    if not horse_numbers:
        reasons.append(
            "no horse numbers found"
        )

    return len(reasons) == 0, reasons


def validate_dataset(
    rows: List[Dict[str, Any]],
) -> Tuple[
    List[Dict[str, Any]],
    List[Dict[str, Any]],
]:
    races = group_by_race(rows)

    clean_rows: List[Dict[str, Any]] = []
    review: List[Dict[str, Any]] = []

    for race_key, race_rows in sorted(
        races.items()
    ):
        valid, reasons = validate_race(
            race_key,
            race_rows,
        )

        if valid:
            clean_rows.extend(race_rows)

        else:
            review.append(
                {
                    "race_key": race_key,
                    "horse_rows": len(race_rows),
                    "reasons": reasons,
                }
            )

    return clean_rows, review


def save_json(
    path: Path,
    data: Any,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            data,
            f,
            indent=4,
            ensure_ascii=False,
        )


def print_summary(
    rows: List[Dict[str, Any]],
    clean_rows: List[Dict[str, Any]],
    review: List[Dict[str, Any]],
) -> None:
    original_races = {
        row.get("race_key")
        for row in rows
        if row.get("race_key")
    }

    clean_races = {
        row.get("race_key")
        for row in clean_rows
        if row.get("race_key")
    }

    print("\n" + "=" * 60)
    print("DATASET VALIDATION COMPLETE")
    print("=" * 60)

    print(
        f"Original races: "
        f"{len(original_races)}"
    )

    print(
        f"Original horse rows: "
        f"{len(rows)}"
    )

    print(
        f"Clean races: "
        f"{len(clean_races)}"
    )

    print(
        f"Clean horse rows: "
        f"{len(clean_rows)}"
    )

    print(
        f"Rejected races: "
        f"{len(review)}"
    )

    if review:
        print("\nREJECTED RACES")

        for item in review:
            print(
                f"  {item['race_key']}"
            )

            for reason in item["reasons"]:
                print(
                    f"    - {reason}"
                )

    print(
        f"\nSaved clean dataset: "
        f"{CLEAN_DATASET_FILE}"
    )

    print(
        f"Saved review file: "
        f"{REVIEW_FILE}"
    )


def main() -> None:
    print("\n" + "=" * 60)
    print("VALIDATING HORSE RACING TRAINING DATASET")
    print("=" * 60)

    rows = load_dataset()

    clean_rows, review = validate_dataset(
        rows
    )

    save_json(
        CLEAN_DATASET_FILE,
        clean_rows,
    )

    save_json(
        REVIEW_FILE,
        review,
    )

    print_summary(
        rows,
        clean_rows,
        review,
    )


if __name__ == "__main__":
    main()
