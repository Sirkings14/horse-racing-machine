from __future__ import annotations

import json
from datetime import date, datetime, timezone
import re
from pathlib import Path

from src.model.logistic_model import LogisticModel

BASE_DIR = Path(__file__).resolve().parents[2]
PROGRAM_DIR = BASE_DIR / "data" / "structured" / "programs"
DATASET_FILE = BASE_DIR / "data" / "dataset" / "training_dataset_clean.json"
MODEL_DIR = BASE_DIR / "data" / "model"
OUTPUT_FILE = MODEL_DIR / "latest_prediction.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def race_metadata(program):
    race = program.get("race") or {}
    return {
        "date": program.get("date") or race.get("date"),
        "track": race.get("track") or program.get("track"),
        "race_number": (
            race.get("race_number")
            if race.get("race_number") is not None
            else program.get("race_number")
        ),
        "race_name": race.get("race_name") or program.get("race_name"),
        "race_type": race.get("race_type") or program.get("race_type"),
        "distance": race.get("distance") or program.get("distance"),
        "runners_count": race.get("runners_count") or program.get("runners_count"),
    }


def race_key(program):
    meta = race_metadata(program)
    date = meta["date"]
    track = meta["track"]
    number = meta["race_number"]

    if not date or not track or number is None:
        return None

    try:
        number = int(number)
    except (TypeError, ValueError):
        return None

    return f"{str(date).strip()}|{str(track).strip().upper()}|{number}"


def has_usable_race_metadata(program):
    meta = race_metadata(program)
    return (
        bool(meta["date"])
        and bool(meta["track"])
        and meta["race_number"] is not None
        and bool(program.get("horses"))
        and race_key(program) is not None
    )


def program_to_rows(program):
    meta = race_metadata(program)
    rankings = program.get("rankings") or {}
    positions = {}

    for name in ("favorites", "form", "class", "progress", "regularity"):
        positions[name] = {}
        for i, value in enumerate(rankings.get(name) or [], 1):
            try:
                positions[name][int(value)] = i
            except (TypeError, ValueError):
                pass

    rows = []
    for horse in program.get("horses") or []:
        try:
            number = int(horse.get("number"))
        except (TypeError, ValueError):
            continue

        if number <= 0:
            continue

        ranks = {
            f"{name}_rank": positions[name].get(number)
            for name in positions
        }
        rank_values = [value for value in ranks.values() if value is not None]

        rows.append(
            {
                "race_key": race_key(program),
                "date": meta["date"],
                "track": meta["track"],
                "race_number": meta["race_number"],
                "race_name": meta["race_name"],
                "race_type": meta["race_type"],
                "distance": meta["distance"],
                "runners_count": meta["runners_count"],
                "horse_number": number,
                "horse_name": horse.get("horse"),
                "horse_description": horse.get("description"),
                **ranks,
                "ranking_average": (
                    sum(rank_values) / len(rank_values)
                    if rank_values
                    else None
                ),
                "ranking_presence": len(rank_values),
            }
        )

    return rows


def normalize_race_date(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for candidate in (text[:10], text):
        try:
            return date.fromisoformat(candidate)
        except ValueError:
            pass
    match = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", text)
    if match:
        year, month, day = map(int, match.groups())
        try:
            return date(year, month, day)
        except ValueError:
            return None
    return None


def program_race_date(program):
    return normalize_race_date(race_metadata(program)["date"])

def today_utc():
    # LONAB/PMU-B operations follow Burkina Faso local time (UTC+0), so UTC is
    # intentionally used as the operational date source.
    return datetime.now(timezone.utc).date()


def program_sort_key(program):
    date = race_metadata(program)["date"]
    if not date:
        return ""

    try:
        return datetime.fromisoformat(str(date).replace("Z", "+00:00")).isoformat()
    except ValueError:
        return str(date)


def main():
    historical = {
        str(row.get("race_key"))
        for row in load_json(DATASET_FILE)
        if row.get("race_key")
    }

    models = {
        depth: LogisticModel.from_dict(
            load_json(MODEL_DIR / f"top{depth}_model.json")
        )
        for depth in (3, 4, 5)
    }

    programs = []
    skipped_invalid_metadata = []

    for path in PROGRAM_DIR.glob("*.json"):
        try:
            payload = load_json(path)
        except Exception as error:
            print(f"Skipping unreadable program {path.name}: {error}")
            continue

        if not isinstance(payload, dict):
            continue

        if not has_usable_race_metadata(payload):
            skipped_invalid_metadata.append(path.name)
            continue

        programs.append((path, payload))

    if not programs:
        raise ValueError(
            "No structured program with usable date, track, race number, "
            "and horses is available for prediction."
        )

    if skipped_invalid_metadata:
        print(
            "Skipped "
            f"{len(skipped_invalid_metadata)} program(s) with incomplete race metadata."
        )
        print("Newest invalid program files:")
        for name in sorted(skipped_invalid_metadata)[-10:]:
            print(f"  - {name}")

    today = today_utc()

    # Predict the nearest eligible race first. Never select a stale program.
    eligible = [
        item
        for item in programs
        if race_key(item[1]) not in historical
        and program_race_date(item[1]) is not None
        and program_race_date(item[1]) >= today
    ]

    eligible.sort(
        key=lambda item: (
            program_race_date(item[1]),
            int(race_metadata(item[1])["race_number"]),
        ),
    )

    if not eligible:
        result = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": "no_eligible_future_race",
            "today": today.isoformat(),
            "recommended_numbers": [],
            "adaptive_top_count": 0,
            "ranked_horses": [],
        }
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_FILE.write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(
            "No current or future unmatched race is available for prediction. "
            "Stale programs were not predicted."
        )
        return

    selected = eligible[0]
    mode = "current_or_future_unmatched"

    path, program = selected
    key = race_key(program)
    rows = program_to_rows(program)

    if not key or not rows:
        raise ValueError(
            f"Selected program {path.name} does not contain a usable race."
        )

    probabilities = {
        depth: models[depth].predict_proba(rows)
        for depth in (3, 4, 5)
    }

    ranked = []

    for index, row in enumerate(rows):
        p3, p4, p5 = (
            float(probabilities[depth][index])
            for depth in (3, 4, 5)
        )
        score = 0.5 * p3 + 0.3 * p4 + 0.2 * p5

        ranked.append(
            {
                "horse_number": int(row["horse_number"]),
                "horse_name": row.get("horse_name"),
                "probability_top3": round(p3, 6),
                "probability_top4": round(p4, 6),
                "probability_top5": round(p5, 6),
                "ensemble_score": round(score, 6),
            }
        )

    ranked.sort(
        key=lambda item: (
            -item["ensemble_score"],
            item["horse_number"],
        )
    )

    for index, item in enumerate(ranked, 1):
        item["predicted_rank"] = index

    adaptive = 5

    if len(ranked) >= 5:
        if (
            ranked[2]["probability_top3"]
            - ranked[3]["probability_top3"]
            >= 0.12
        ):
            adaptive = 3
        elif (
            ranked[3]["probability_top4"]
            - ranked[4]["probability_top4"]
            >= 0.10
        ):
            adaptive = 4

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "today": today.isoformat(),
        "source_program": path.name,
        "race_key": key,
        "race": race_metadata(program),
        "recommended_numbers": [
            item["horse_number"]
            for item in ranked[:adaptive]
        ],
        "adaptive_top_count": adaptive,
        "top3_numbers": [
            item["horse_number"]
            for item in ranked[:3]
        ],
        "ranked_horses": ranked,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Race: {result['race_key']}")
    print(f"Adaptive recommendation ({adaptive}): {result['recommended_numbers']}")


if __name__ == "__main__":
    main()
