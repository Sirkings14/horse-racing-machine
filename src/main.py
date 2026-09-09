from src.scraper import run_scraper

from src.processors.process_pdfs import (
    process_all_pdfs
)

from src.parsers.program_parser import (
    process_all_programs
)

from src.parsers.results_parser import (
    process_all_results
)


def main():

    print("\n" + "=" * 60)
    print("STARTING HORSE RACING MACHINE")
    print("=" * 60)

    print("\nSTEP 1: SCRAPING LONAB DATA")

    run_scraper()

    print("\nSTEP 2: PROCESSING RACE PDFs")

    process_all_pdfs()

    print("\nSTEP 3: PARSING PROGRAM DATA")

    process_all_programs()

    print("\nSTEP 4: PARSING RESULT DATA")

    process_all_results()

    print("\n" + "=" * 60)
    print("HORSE RACING MACHINE FINISHED SUCCESSFULLY")
    print("=" * 60)


if __name__ == "__main__":
    main()
