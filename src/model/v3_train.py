from __future__ import annotations
import json
from pathlib import Path
from src.model.historical_profile import build_walk_forward_profiles
from src.model.v3_model import fit_v3_model
BASE_DIR=Path(__file__).resolve().parents[2]
DATASET_FILE=BASE_DIR/"data/dataset/training_dataset_clean.json"
OUTPUT_FILE=BASE_DIR/"data/model/v3_models.json"
def main():
    rows=json.loads(DATASET_FILE.read_text(encoding="utf-8"))
    profiled=build_walk_forward_profiles(rows)
    models={}
    for name,target in (("winner","won"),("top3","top3"),("top5","top5")):
        models[name]=fit_v3_model(profiled,target_field=target).to_dict()
    payload={"model_version":"v3-evidence-no-press","press_dependency":False,"post_race_feature_policy":"hard_exclusion","models":models}
    OUTPUT_FILE.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding="utf-8")
    print(f"Saved V3 model bundle: {OUTPUT_FILE}")
if __name__=="__main__": main()
