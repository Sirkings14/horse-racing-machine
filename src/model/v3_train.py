from __future__ import annotations
import json
from pathlib import Path
from src.model.historical_profile import build_walk_forward_profiles
from src.model.v3_model import fit_v3_model
BASE_DIR=Path(__file__).resolve().parents[2]
DATASET_FILE=BASE_DIR/"data/dataset/training_dataset_clean.json"
OUTPUT_FILE=BASE_DIR/"data/model/v3_model.json"
def main():
    rows=json.loads(DATASET_FILE.read_text(encoding="utf-8"))
    model=fit_v3_model(build_walk_forward_profiles(rows))
    OUTPUT_FILE.parent.mkdir(parents=True,exist_ok=True); OUTPUT_FILE.write_text(json.dumps(model.to_dict(),indent=2,ensure_ascii=False),encoding="utf-8")
    print(f"Saved V3 evidence model: {OUTPUT_FILE}")
if __name__=="__main__": main()
