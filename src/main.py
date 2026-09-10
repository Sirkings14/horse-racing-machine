from src.scraper import run_scraper
from src.processors.process_pdfs import process_all_pdfs
from src.parsers.program_parser import process_all_programs
from src.parsers.results_parser import process_all_results
from src.matching.race_matcher import run_matching


def main():

    print("\n" + "=" * 60)
    print("STARTING HORSE RACING MACHINE")
    print("=" * 60)

    # ========================================================
    # STEP 1: SCRAPING
    # ========================================================

    print("\nSTEP 1: SCRAPING LONAB DATA")

    run_scraper()

    # ========================================================
    # STEP 2: PDF PROCESSING
    # ========================================================

    print("\nSTEP 2: PROCESSING RACE PDFs")

    process_all_pdfs()

    # ========================================================
    # STEP 3: PARSING PROGRAMS
    # ========================================================

    print("\nSTEP 3: PARSING PROGRAM DATA")

    process_all_programs()

    # ========================================================
    # STEP 4: PARSING RESULTS
    # ========================================================

    print("\nSTEP 4: PARSING RESULT DATA")

    process_all_results()

    # ========================================================
    # STEP 5: MATCHING PROGRAMS WITH RESULTS
    # ========================================================

    print("\nSTEP 5: MATCHING PROGRAMS WITH RESULTS")

    run_matching(
        programs_path="data/structured/programs",
        results_path="data/structured/results",
        output_path="data/matched/matched_races.json",
        review_path="data/matched/match_review.json",
    )

    # ========================================================
    # COMPLETE
    # ========================================================

    print("\n" + "=" * 60)
    print("HORSE RACING MACHINE FINISHED SUCCESSFULLY")
    print("=" * 60)


if __name__ == "__main__":
    main()
