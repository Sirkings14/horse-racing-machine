from src.processors.process_pdfs import process_all_pdfs
from src.scraper import run_scraper
from src.parsers.program_parser import process_all_programs


def main():

    print("STARTING HORSE RACING MACHINE")

    print("\n" + "=" * 60)
    print("STEP 1: SCRAPING LONAB DATA")
    print("=" * 60)

    run_scraper()

    print("\n" + "=" * 60)
    print("STEP 2: PROCESSING RACE PDFs")
    print("=" * 60)

    process_all_pdfs()

    print("\n" + "=" * 60)
    print("STEP 3: PARSING PROGRAM DATA")
    print("=" * 60)

    process_all_programs()

    print("\n" + "=" * 60)
    print("HORSE RACING MACHINE FINISHED SUCCESSFULLY")
    print("=" * 60)


if __name__ == "__main__":
    main()
