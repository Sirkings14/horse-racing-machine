from __future__ import annotations

import json
from datetime import date, datetime, timezone
import re
from pathlib import Path

from src.live.registry import eligible_races, mark_predicted, LIVE_DIR
from src.model.logistic_model import LogisticModel

BASE_DIR = Path(__file__).resolve().parents[2]
DATASET_FILE = BASE_DIR / "data" / "dataset" / "training_dataset_clean.json"
MODEL_DIR = BASE_DIR / "data" / "model"
PREDICTIONS_DIR = BASE_DIR / "data" / "predictions"
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
    race_date = meta["date"]
    track = meta["track"]
    number = meta["race_number"]
    if not race_date or not track or number is None:
        return None
    try:
        number = int(number)
    except (TypeError, ValueError):
        return None
    return f"{str(race_date).strip()}|{str(track).strip().upper()}|{number}"


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

        ranks = {f"{name}_rank": positions[name].get(number) for name in positions}
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
                "ranking_average": (sum(rank_values) / len(rank_values) if rank_values else None),
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


def today_utc():
    return datetime.now(timezone.utc).date()


def write_prediction(result):
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    key = result.get("race_key")
    if key:
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(key))
        archive_path = PREDICTIONS_DIR / f"{safe_name}.json"
        archive_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")


def no_prediction(reason: str, **extra):
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "prediction_unavailable",
        "reason": reason,
        "recommended_numbers": [],
        "adaptive_top_count": 0,
        "ranked_horses": [],
        **extra,
    }
    write_prediction(result)
    print(f"Prediction unavailable: {reason}")
    return result


def main():
    try:
        load_json(DATASET_FILE)
    except Exception as error:
        return no_prediction(f"training_dataset_unavailable: {error}")

    models = {}
    for depth in (3, 4, 5):
        model_path = MODEL_DIR / f"top{depth}_model.json"
        try:
            models[depth] = LogisticModel.from_dict(load_json(model_path))
        except Exception as error:
            return no_prediction(f"model_unavailable_top{depth}: {error}")

    today = today_utc()
    races = eligible_races(today.isoformat())
    if not races:
        return no_prediction(
            "no_validated_current_or_future_race",
            today=today.isoformat(),
            live_manifest=str(LIVE_DIR / "live_manifest.json"),
        )

    selected_entry = races[0]
    structured_path = LIVE_DIR / str(selected_entry["structured_file"])
    try:
        program = load_json(structured_path)
    except Exception as error:
        return no_prediction(
            f"live_program_unreadable: {error}",
            race_key=selected_entry.get("race_key"),
        )

    meta = race_metadata(program)
    actual_date = normalize_race_date(meta["date"])
    rows = program_to_rows(program)
    key = race_key(program)

    if actual_date is None or actual_date < today:
        return no_prediction("live_program_is_stale", race_key=key, today=today.isoformat())
    if not key or not rows:
        return no_prediction("live_program_missing_usable_race_data", race_key=key)

    probabilities = {depth: models[depth].predict_proba(rows) for depth in (3, 4, 5)}
    ranked = []
    for index, row in enumerate(rows):
        p3, p4, p5 = (float(probabilities[depth][index]) for depth in (3, 4, 5))
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

    ranked.sort(key=lambda item: (-item["ensemble_score"], item["horse_number"]))
    for index, item in enumerate(ranked, 1):
        item["predicted_rank"] = index

    adaptive = 5
    if len(ranked) >= 5:
        if ranked[2]["probability_top3"] - ranked[3]["probability_top3"] >= 0.12:
            adaptive = 3
        elif ranked[3]["probability_top4"] - ranked[4]["probability_top4"] >= 0.10:
            adaptive = 4

    model_registry_path = MODEL_DIR / "model_registry.json"
    model_version = "unknown"
    try:
        registry = load_json(model_registry_path)
        model_version = registry.get("champion_version", "unknown")
    except Exception:
        pass

    result = {
        "prediction_id": f"{key}|{datetime.now(timezone.utc).isoformat()}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_version": model_version,
        "mode": "live_registry_prediction",
        "today": today.isoformat(),
        "source_program": selected_entry.get("source_file"),
        "source_url": selected_entry.get("source_url"),
        "race_key": key,
        "race": meta,
        "recommended_numbers": [item["horse_number"] for item in ranked[:adaptive]],
        "adaptive_top_count": adaptive,
        "top3_numbers": [item["horse_number"] for item in ranked[:3]],
        "ranked_horses": ranked,
        "live_manifest": str(LIVE_DIR / "live_manifest.json"),
    }

    write_prediction(result)
    mark_predicted(key, str((PREDICTIONS_DIR / f"{re.sub(r'[^A-Za-z0-9_.-]+', '_', str(key))}.json").relative_to(BASE_DIR)))

    print(f"Live race: {result['race_key']}")
    print(f"Adaptive recommendation ({adaptive}): {result['recommended_numbers']}")
    return result


if __name__ == "__main__":
    main()
