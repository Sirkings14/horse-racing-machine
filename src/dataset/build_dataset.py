import json
import hashlib
from pathlib import Path


STRUCTURED_PROGRAMS = Path("data/structured/programs")
STRUCTURED_RESULTS = Path("data/structured/results")
OUTPUT_FILE = Path("data/dataset/training_dataset.json")


def load_json_files(folder):
    records = []

    for file_path in sorted(folder.glob("*.json")):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            data["_file_path"] = str(file_path)
            records.append(data)

        except Exception as e:
            print(f"Failed to load {file_path.name}: {e}")

    return records


def make_program_key(program):
    race = program.get("race", {})

    return (
        program.get("date"),
        race.get("track"),
        race.get("race_number"),
        race.get("race_name"),
    )


def make_result_key(result):
    return (
        result.get("date"),
        result.get("meeting"),
        result.get("track"),
    )


def deduplicate_programs(programs):
    unique = {}

    for program in programs:
        key = make_program_key(program)

        if key not in unique:
            unique[key] = program
        else:
            print(
                f"Duplicate program ignored: "
                f"{program.get('_file_path')}"
            )

    return list(unique.values())


def deduplicate_results(results):
    unique = {}

    for result in results:
        key = make_result_key(result)

        if key not in unique:
            unique[key] = result
        else:
            print(
                f"Duplicate result ignored: "
                f"{result.get('_file_path')}"
            )

    return list(unique.values())


def build_horse_features(program):
    rankings = program.get("rankings", {})

    favorites = rankings.get("favorites", [])
    form = rankings.get("form", [])
    race_class = rankings.get("class", [])
    progress = rankings.get("progress", [])
    regularity = rankings.get("regularity", [])

    horses = []

    for horse in program.get("horses", []):

        number = horse.get("number")

        horse_data = {
            "number": number,
            "horse": horse.get("horse"),
            "description": horse.get("description"),
            "favorite_rank": (
                favorites.index(number) + 1
                if number in favorites
                else None
            ),
            "form_rank": (
                form.index(number) + 1
                if number in form
                else None
            ),
            "class_rank": (
                race_class.index(number) + 1
                if number in race_class
                else None
            ),
            "progress_rank": (
                progress.index(number) + 1
                if number in progress
                else None
            ),
            "regularity_rank": (
                regularity.index(number) + 1
                if number in regularity
                else None
            ),
        }

        horses.append(horse_data)

    return horses


def build_dataset():
    print("\n" + "=" * 60)
    print("BUILDING TRAINING DATASET")
    print("=" * 60)

    programs = load_json_files(STRUCTURED_PROGRAMS)
    results = load_json_files(STRUCTURED_RESULTS)

    print(f"\nPrograms loaded: {len(programs)}")
    print(f"Results loaded: {len(results)}")

    programs = deduplicate_programs(programs)
    results = deduplicate_results(results)

    print(f"\nUnique programs: {len(programs)}")
    print(f"Unique results: {len(results)}")

    dataset = []

    for program in programs:

        race = program.get("race", {})

        horses = build_horse_features(program)

        record = {
            "date": program.get("date"),
            "race_name": race.get("race_name"),
            "track": race.get("track"),
            "race_number": race.get("race_number"),
            "race_type": race.get("race_type"),
            "distance": race.get("distance"),
            "prize_euros": race.get("prize_euros"),
            "runners_count": race.get("runners_count"),
            "horses": horses,
            "published_arrival": program.get(
                "published_arrival",
                []
            ),
            "source_file": program.get("source_file"),
        }

        dataset.append(record)

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            dataset,
            f,
            indent=4,
            ensure_ascii=False
        )

    print("\n" + "=" * 60)
    print("DATASET BUILD COMPLETE")
    print("=" * 60)

    print(f"\nTraining records: {len(dataset)}")
    print(f"Saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    build_dataset()
