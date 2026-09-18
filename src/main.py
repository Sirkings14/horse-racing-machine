from pathlib import Path
import argparse
import json

from src.scraper import run_scraper
from src.processors.process_pdfs import process_all_pdfs
from src.parsers.program_parser import process_all_programs
from src.parsers.results_parser import process_all_results
from src.matching.race_matcher import run_matching
from src.validators.pipeline_validator import validate_pipeline
from src.dataset.build_dataset import main as build_dataset
from src.dataset.dataset_validator import main as validate_dataset
from src.model.train_model import main as train_model
from src.model.backtest import main as run_backtest
from src.model.order_backtest import main as run_order_backtest
from src.model.promote_model import main as promote_model
from src.model.predict_latest import main as generate_prediction
from src.memory.update_memory import main as update_memory
from src.notifications.telegram import send_latest_prediction
from src.live.collector import collect_live_programs
from src.learning.evaluate_predictions import main as evaluate_predictions
from src.model.autopilot_guard import main as run_autopilot_guard
from src.model.race_difficulty import main as run_race_difficulty

BASE_DIR = Path(__file__).resolve().parents[1]
REVIEW_FILE = BASE_DIR / "data" / "dataset" / "dataset_review.json"


def print_step(number, title):
    print("\n" + "=" * 60)
    print(f"STEP {number}: {title}")
    print("=" * 60)


def assert_dataset_clean():
    """Ensure validation produced usable clean data without blocking on isolated bad races."""
    with REVIEW_FILE.open("r", encoding="utf-8") as handle:
        review = json.load(handle)
    if not isinstance(review, list):
        raise RuntimeError("dataset_review.json must contain a list.")

    clean_dataset_file = BASE_DIR / "data" / "dataset" / "training_dataset_clean.json"
    if not clean_dataset_file.exists():
        raise RuntimeError("Training dataset validation did not produce a clean dataset.")
    with clean_dataset_file.open("r", encoding="utf-8") as handle:
        clean_rows = json.load(handle)
    if not isinstance(clean_rows, list) or not clean_rows:
        raise RuntimeError("Training dataset validation produced no usable clean horse rows.")

    clean_races = {row.get("race_key") for row in clean_rows if isinstance(row, dict) and row.get("race_key")}
    if not clean_races:
        raise RuntimeError("Training dataset validation produced no usable clean races.")
    if review:
        print(f"Training dataset validation quarantined {len(review)} malformed/incomplete race(s).")
        for item in review:
            print(f"  Skipping {item.get('race_key', 'unknown race')}: " + "; ".join(item.get("reasons", [])))
    else:
        print("Training dataset validation passed: 0 rejected races.")
    print(f"Proceeding with {len(clean_races)} clean race(s) and {len(clean_rows)} clean horse rows.")


def rebuild_knowledge():
    print_step(1, "SCRAPING LONAB DATA")
    run_scraper()
    print_step(2, "PROCESSING RACE PDFs")
    process_all_pdfs()
    print_step(3, "PARSING PROGRAM DATA")
    process_all_programs()
    print_step(4, "PARSING RESULT DATA")
    process_all_results()
    print_step(5, "VALIDATING PIPELINE DATA")
    validation = validate_pipeline(programs_path="data/structured/programs", results_path="data/structured/results")
    if not validation.get("valid"):
        raise RuntimeError("Pipeline validation failed.")
    print_step(6, "MATCHING PROGRAMS WITH RESULTS")
    run_matching(
        programs_path="data/structured/programs", results_path="data/structured/results",
        output_path="data/matched/matched_races.json", review_path="data/matched/match_review.json",
    )
    print_step(7, "BUILDING TRAINING DATASET")
    build_dataset()
    print_step(8, "VALIDATING TRAINING DATASET")
    validate_dataset()
    assert_dataset_clean()
    print_step(9, "UPDATING VERIFIED RACE MEMORY")
    update_memory()


def run_prediction_cycle():
    print_step(1, "DISCOVERING LIVE PROGRAMS")
    collect_live_programs()
    print_step(2, "GENERATING PREDICTION FROM LIVE REGISTRY")
    generate_prediction()
    print_step(3, "SENDING TELEGRAM PREDICTION")
    send_latest_prediction()


def run_results_cycle():
    print_step(1, "REBUILDING VERIFIED RESULTS KNOWLEDGE")
    rebuild_knowledge()
    print_step(2, "VERIFYING STORED PREDICTIONS AGAINST RESULTS")
    evaluate_predictions()
    print_step(3, "TRAINING UPDATED CHALLENGER + ORDER ENGINE")
    candidate_version = train_model()
    print_step(4, "RUNNING WALK-FORWARD TOP-3/4/5 BACKTEST")
    run_backtest()
    print_step(5, "RUNNING FINISHING-ORDER HOLDOUT BACKTEST")
    run_order_backtest()
    print_step(6, "PROMOTING ONLY A MEASURED CHALLENGER")
    promote_model(candidate_version)
    print_step(7, "UPDATING RACE DIFFICULTY REPORT")
    run_race_difficulty()
    print_step(8, "UPDATING AUTOPILOT HEALTH GUARD")
    run_autopilot_guard()


def run_learning_cycle():
    rebuild_knowledge()
    print_step(10, "TRAINING ISOLATED CHALLENGER MODELS + ORDER ENGINE")
    candidate_version = train_model()
    print_step(11, "RUNNING WALK-FORWARD TOP-3/4/5 BACKTEST")
    run_backtest()
    print_step(12, "RUNNING FINISHING-ORDER HOLDOUT BACKTEST")
    run_order_backtest()
    print_step(13, "PROMOTING ONLY A MEASURED CHALLENGER")
    promote_model(candidate_version)
    print_step(14, "VERIFYING STORED PREDICTIONS AGAINST RESULTS")
    evaluate_predictions()
    print_step(15, "UPDATING RACE DIFFICULTY REPORT")
    run_race_difficulty()
    print_step(16, "UPDATING AUTOPILOT HEALTH GUARD")
    run_autopilot_guard()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["predict", "results", "full"], default="full")
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print(f"STARTING AUTONOMOUS HORSE RACING MACHINE: {args.mode}")
    print("=" * 60)

    if args.mode == "predict":
        run_prediction_cycle()
    elif args.mode == "results":
        run_results_cycle()
    else:
        run_learning_cycle()
        print_step(15, "GENERATING LIVE PREDICTION")
        collect_live_programs()
        generate_prediction()
        print_step(16, "SENDING TELEGRAM PREDICTION")
        send_latest_prediction()

    print("\n" + "=" * 60)
    print("AUTONOMOUS HORSE RACING MACHINE FINISHED SUCCESSFULLY")
    print("=" * 60)


if __name__ == "__main__":
    main()
