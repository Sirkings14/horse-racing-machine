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
from src.model.predict_latest import main as generate_prediction
from src.memory.update_memory import main as update_memory
from src.notifications.telegram import send_latest_prediction
from src.live.collector import collect_live_programs

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

    clean_races = {
        row.get("race_key")
        for row in clean_rows
        if isinstance(row, dict) and row.get("race_key")
    }
    if not clean_races:
        raise RuntimeError("Training dataset validation produced no usable clean races.")

    if review:
        print(f"Training dataset validation quarantined {len(review)} malformed/incomplete race(s).")
        for item in review:
            print(
                f"  Skipping {item.get('race_key', 'unknown race')}: "
                + "; ".join(item.get("reasons", []))
            )
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
    validation = validate_pipeline(
        programs_path="data/structured/programs",
        results_path="data/structured/results",
    )
    if not validation.get("valid"):
        raise RuntimeError("Pipeline validation failed.")
    print_step(6, "MATCHING PROGRAMS WITH RESULTS")
    run_matching(
        programs_path="data/structured/programs",
        results_path="data/structured/results",
        output_path="data/matched/matched_races.json",
        review_path="data/matched/match_review.json",
    )
    print_step(7, "BUILDING TRAINING DATASET")
    build_dataset()
    print_step(8, "VALIDATING TRAINING DATASET")
    validate_dataset()
    assert_dataset_clean()
    print_step(9, "UPDATING VERIFIED RACE MEMORY")
    update_memory()


def run_prediction_cycle():
    # Prediction is intentionally independent from the historical rebuild.
    # A live source failure must not destroy or rewrite the trained knowledge.
    print_step(1, "DISCOVERING LIVE PROGRAMS")
    collect_live_programs()
    print_step(2, "GENERATING PREDICTION FROM LIVE REGISTRY")
    generate_prediction()
    print_step(3, "SENDING TELEGRAM PREDICTION")
    send_latest_prediction()


def run_learning_cycle():
    rebuild_knowledge()
    print_step(10, "TRAINING ADAPTIVE TOP-3 TOP-4 TOP-5 MODELS")
    train_model()
    print_step(11, "RUNNING WALK-FORWARD BACKTEST")
    run_backtest()


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
        rebuild_knowledge()
    else:
        run_learning_cycle()
        print_step(12, "GENERATING LIVE PREDICTION")
        collect_live_programs()
        generate_prediction()
        print_step(13, "SENDING TELEGRAM PREDICTION")
        send_latest_prediction()

    print("\n" + "=" * 60)
    print("AUTONOMOUS HORSE RACING MACHINE FINISHED SUCCESSFULLY")
    print("=" * 60)


if __name__ == "__main__":
    main()
