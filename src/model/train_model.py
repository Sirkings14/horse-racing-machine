from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from src.model.logistic_model import fit_top3_model


BASE_DIR = Path(__file__).resolve().parents[2]
DATASET_FILE = BASE_DIR / "data" / "dataset" / "training_dataset_clean.json"
MODEL_FILE = BASE_DIR / "data" / "model" / "top3_model.json"


def load_rows() -> List[Dict[str, Any]]:
    with DATASET_FILE.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError("Clean training dataset must be a JSON list.")
    return data


def main() -> None:
    rows = load_rows()
    model = fit_top3_model(rows)

    MODEL_FILE.parent.mkdir(parents=True, exist_ok=True)
    MODEL_FILE.write_text(
        json.dumps(model.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\n" + "=" * 60)
    print("TRAINING FINAL TOP-3 MODEL")
    print("=" * 60)
    print(f"Training rows: {len(rows)}")
    print(f"Features: {len(model.feature_names)}")
    print("Coefficients:")
    for name, coefficient in zip(model.feature_names, model.coefficients):
        print(f"  {name}: {coefficient:.6f}")
    print(f"Saved model: {MODEL_FILE}")


if __name__ == "__main__":
    main()
