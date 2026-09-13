from __future__ import annotations

import json
from pathlib import Path

from src.model.logistic_model import fit_top3_model
from src.model.model_registry import CHALLENGER_DIR, new_candidate_version, record_candidate

BASE_DIR = Path(__file__).resolve().parents[2]
DATASET_FILE = BASE_DIR / "data" / "dataset" / "training_dataset_clean.json"


def main() -> str:
    rows = json.loads(DATASET_FILE.read_text(encoding="utf-8"))
    version = new_candidate_version()
    candidate_dir = CHALLENGER_DIR / version
    candidate_dir.mkdir(parents=True, exist_ok=False)

    for depth in (3, 4, 5):
        model = fit_top3_model(rows, target_field=f"top{depth}")
        path = candidate_dir / f"top{depth}_model.json"
        path.write_text(
            json.dumps(model.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"Saved challenger Top-{depth} model: {path}")

    record_candidate(version, {"training_races": len({row.get('race_key') for row in rows if row.get('race_key')})})
    print(f"Challenger version ready: {version}")
    return version


if __name__ == "__main__":
    main()
