from src.processors.process_pdfs import process_all_pdfs
from src.scraper import run_scraper


def main():

    print("Starting Horse Racing Machine")

    run_scraper()

    print("Horse Racing Machine finished successfully")


if __name__ == "__main__":
    main()
