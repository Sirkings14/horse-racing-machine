from src.scraper import run_scraper

from src.processors.pdf_processor import run_pdf_processor
from src.parsers.program_parser import run_program_parser
from src.parsers.result_parser import run_result_parser
from src.matching.race_matcher import run_race_matcher


def main():

    print("=" * 60)
    print("STARTING HORSE RACING MACHINE")
    print("=" * 60)

    # ========================================================
    # STEP 1: SCRAPE LONAB DATA
    # ========================================================

    print("\nSTEP 1: SCRAPING LONAB DATA")

    run_scraper()


    # ========================================================
    # STEP 2: PROCESS RACE PDFs
    # ========================================================

    print("\nSTEP 2: PROCESSING RACE PDFs")

    run_pdf_processor()


    # ========================================================
    # STEP 3: PARSE PROGRAM DATA
    # ========================================================

    print("\nSTEP 3: PARSING PROGRAM DATA")

    run_program_parser()


    # ========================================================
    # STEP 4: PARSE RESULT DATA
    # ========================================================

    print("\nSTEP 4: PARSING RESULT DATA")

    run_result_parser()


    # ========================================================
    # STEP 5: MATCH PROGRAMS WITH RESULTS
    # ========================================================

    print("\nSTEP 5: MATCHING PROGRAMS WITH RESULTS")

    run_race_matcher()


    print("\n" + "=" * 60)
    print("HORSE RACING MACHINE FINISHED SUCCESSFULLY")
    print("=" * 60)


if __name__ == "__main__":
    main()
