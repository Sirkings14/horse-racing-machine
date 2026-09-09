import os
import re
import hashlib
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse


PROGRAM_URL = "https://www.lonab.bf/programme-pmub"
RESULTS_URL = "https://www.lonab.bf/resultats-gains-ecd"


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120 Safari/537.36"
    )
}


def ensure_directories():
    os.makedirs("data/raw/programs", exist_ok=True)
    os.makedirs("data/raw/results", exist_ok=True)


def safe_filename(url, prefix):
    """
    Creates a short, safe filename.
    Never uses webpage text.
    """

    parsed = urlparse(url)

    original_name = os.path.basename(parsed.path)

    if not original_name:
        original_name = "document.pdf"

    original_name = original_name.split("?")[0]

    if not original_name.lower().endswith(".pdf"):
        original_name += ".pdf"

    original_name = re.sub(
        r"[^a-zA-Z0-9._-]",
        "_",
        original_name
    )

    if len(original_name) > 100:
        original_name = original_name[:100] + ".pdf"

    url_hash = hashlib.md5(
        url.encode("utf-8")
    ).hexdigest()[:10]

    date_stamp = datetime.now().strftime("%Y%m%d")

    return f"{prefix}_{date_stamp}_{url_hash}.pdf"


def get_pdf_links(page_url):
    """
    Gets only real PDF links from a LONAB page.
    """

    print(f"Checking: {page_url}")

    response = requests.get(
        page_url,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    pdf_links = []

    for link in soup.find_all("a", href=True):

        href = link.get("href", "").strip()

        if not href:
            continue

        # Ignore anchors
        if href.startswith("#"):
            continue

        absolute_url = urljoin(
            page_url,
            href
        )

        parsed = urlparse(absolute_url)

        # Ignore same-page fragments
        if parsed.fragment:
            absolute_url = absolute_url.split("#")[0]

        # Only accept actual PDF URLs
        if ".pdf" in parsed.path.lower():

            clean_url = absolute_url.split("#")[0]

            if clean_url not in pdf_links:
                pdf_links.append(clean_url)

    return pdf_links


def download_pdf(url, folder, prefix):

    filename = safe_filename(
        url,
        prefix
    )

    filepath = os.path.join(
        folder,
        filename
    )

    # Don't download again if it exists
    if os.path.exists(filepath):

        print(
            f"Already downloaded: {filepath}"
        )

        return filepath

    print(f"Downloading PDF: {url}")

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=60
    )

    response.raise_for_status()

    content_type = response.headers.get(
        "Content-Type",
        ""
    ).lower()

    content = response.content

    # Basic validation
    if (
        "pdf" not in content_type
        and not content.startswith(b"%PDF")
    ):
        print(
            f"Skipped non-PDF response: {url}"
        )

        return None

    with open(
        filepath,
        "wb"
    ) as file:
        file.write(content)

    print(
        f"Saved: {filepath}"
    )

    return filepath


def scrape_programs():

    ensure_directories()

    links = get_pdf_links(
        PROGRAM_URL
    )

    print(
        f"Program PDFs found: {len(links)}"
    )

    downloaded = []

    for url in links:

        try:

            filepath = download_pdf(
                url,
                "data/raw/programs",
                "program"
            )

            if filepath:
                downloaded.append(filepath)

        except Exception as error:

            print(
                f"Program download error: {error}"
            )

    return downloaded


def scrape_results():

    ensure_directories()

    links = get_pdf_links(
        RESULTS_URL
    )

    print(
        f"Result PDFs found: {len(links)}"
    )

    downloaded = []

    for url in links:

        try:

            filepath = download_pdf(
                url,
                "data/raw/results",
                "result"
            )

            if filepath:
                downloaded.append(filepath)

        except Exception as error:

            print(
                f"Result download error: {error}"
            )

    return downloaded


def run_scraper():

    print("=" * 50)
    print("LONAB RACE MACHINE SCRAPER")
    print("=" * 50)

    print("\nSCRAPING PROGRAMS")

    programs = scrape_programs()

    print("\nSCRAPING RESULTS")

    results = scrape_results()

    print("\n" + "=" * 50)

    print(
        f"Programs downloaded: {len(programs)}"
    )

    print(
        f"Results downloaded: {len(results)}"
    )

    print("=" * 50)

    return {
        "programs": programs,
        "results": results
    }


if __name__ == "__main__":
    run_scraper()
