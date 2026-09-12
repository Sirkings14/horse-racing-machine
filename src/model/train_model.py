from __future__ import annotations
import json
from pathlib import Path
from src.model.logistic_model import fit_top3_model

BASE_DIR = Path(__file__).resolve().parents[2]
DATASET_FILE = BASE_DIR / "data" / "dataset" / "training_dataset_clean.json"
MODEL_DIR = BASE_DIR / "data" / "model"

def main() -> None:
    rows = json.loads(DATASET_FILE.read_text(encoding="utf-8"))
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    for depth in (3, 4, 5):
        model = fit_top3_model(rows, target_field=f"top{depth}")
        path = MODEL_DIR / f"top{depth}_model.json"
        path.write_text(json.dumps(model.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Saved Top-{depth} model: {path}")

if __name__ == "__main__":
    main()
