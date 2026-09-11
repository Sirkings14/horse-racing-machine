import os
import re
import hashlib
from datetime import datetime
from urllib.parse import urljoin, urlparse, unquote

import requests
from bs4 import BeautifulSoup


PROGRAM_URL = "https://www.lonab.bf/fr/programme-pmub"
RESULTS_URL = "https://www.lonab.bf/fr/resultats-gains-ecd"

# Number of archive pages to crawl.
# LONAB currently exposes roughly 10 documents per page.
# 16 pages gives us a substantial historical window.
HISTORICAL_PAGES = 16

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120 Safari/537.36"
    )
}


def ensure_directories():
    os.makedirs("data/raw/programs", exist_ok=True)
    os.makedirs("data/raw/results", exist_ok=True)


def normalize_url(url):
    """
    Normalize URLs so duplicate links are treated as the same URL.
    """

    url = url.strip()

    # Remove fragments.
    url = url.split("#")[0]

    # Decode one level of URL encoding.
    decoded = unquote(url)

    return decoded


def url_hash(url):
    """
    Stable hash based only on the source URL.
    """

    normalized = normalize_url(url)

    return hashlib.md5(
        normalized.encode("utf-8")
    ).hexdigest()[:10]


def safe_original_filename(url):
    """
    Get a safe filename from the source URL.
    """

    parsed = urlparse(url)

    original_name = os.path.basename(
        parsed.path
    )

    if not original_name:
        original_name = "document.pdf"

    original_name = unquote(
        original_name
    )

    if not original_name.lower().endswith(".pdf"):
        original_name += ".pdf"

    original_name = re.sub(
        r"[^a-zA-Z0-9._-]",
        "_",
        original_name
    )

    if len(original_name) > 100:
        original_name = (
            original_name[:96] + ".pdf"
        )

    return original_name


def stable_filename(url, prefix):
    """
    Create a stable filename.

    Unlike the previous scraper, this filename does NOT contain
    today's date. The same source URL therefore maps to the same
    local filename every day.
    """

    original_name = safe_original_filename(
        url
    )

    source_hash = url_hash(url)

    stem, _ = os.path.splitext(
        original_name
    )

    return (
        f"{prefix}_"
        f"{stem}_"
        f"{source_hash}.pdf"
    )


def existing_file_for_url(
    url,
    folder,
    prefix,
):
    """
    Find a previously downloaded copy.

    Supports both:
    1. New stable filenames.
    2. Old filenames produced by the previous scraper.
    """

    source_hash = url_hash(url)

    stable_name = stable_filename(
        url,
        prefix
    )

    stable_path = os.path.join(
        folder,
        stable_name
    )

    if os.path.exists(stable_path):
        return stable_path

    # Backward compatibility with files like:
    #
    # program_20260911_032388a005.pdf
    # result_20260911_043a0bb415.pdf
    #
    old_pattern = os.path.join(
        folder,
        f"{prefix}_*_{source_hash}.pdf"
    )

    matches = sorted(
        [
            path
            for path in (
                __import__("glob").glob(
                    old_pattern
                )
            ]
            if os.path.isfile(path)
        ]
    )

    if matches:
        return matches[0]

    return None


def build_archive_page_urls(base_url):
    """
    Build the archive pages.

    Page 0 is the current page.
    Older documents are exposed through ?page=1, ?page=2, etc.
    """

    urls = []

    for page in range(
        HISTORICAL_PAGES
    ):
        if page == 0:
            url = base_url
        else:
            separator = (
                "&"
                if "?" in base_url
                else "?"
            )

            url = (
                f"{base_url}"
                f"{separator}page={page}"
            )

        urls.append(url)

    return urls


def get_pdf_links(page_url):
    """
    Get real PDF links from one LONAB archive page.
    """

    print(
        f"Checking archive page: "
        f"{page_url}"
    )

    response = requests.get(
        page_url,
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    pdf_links = []

    for link in soup.find_all(
        "a",
        href=True,
    ):
        href = link.get(
            "href",
            ""
        ).strip()

        if not href:
            continue

        if href.startswith("#"):
            continue

        absolute_url = urljoin(
            page_url,
            href,
        )

        absolute_url = normalize_url(
            absolute_url
        )

        parsed = urlparse(
            absolute_url
        )

        if not parsed.path.lower().endswith(
            ".pdf"
        ):
            continue

        if absolute_url not in pdf_links:
            pdf_links.append(
                absolute_url
            )

    return pdf_links


def collect_historical_pdf_links(
    base_url
):
    """
    Crawl multiple LONAB archive pages and collect
    unique PDF URLs.
    """

    all_links = []
    seen = set()

    pages_checked = 0

    for page_url in build_archive_page_urls(
        base_url
    ):

        try:
            links = get_pdf_links(
                page_url
            )

            pages_checked += 1

            print(
                f"PDFs found on page: "
                f"{len(links)}"
            )

            new_links = 0

            for link in links:
                normalized = normalize_url(
                    link
                )

                if normalized in seen:
                    continue

                seen.add(
                    normalized
                )

                all_links.append(
                    normalized
                )

                new_links += 1

            print(
                f"New unique PDFs: "
                f"{new_links}"
            )

            # If an archive page has no PDFs,
            # stop walking older pages.
            if not links:
                print(
                    "No PDFs found on this page. "
                    "Stopping archive crawl."
                )
                break

        except Exception as error:
            print(
                f"Archive page error: "
                f"{page_url}"
            )

            print(
                f"Error: {error}"
            )

    print(
        f"Archive pages checked: "
        f"{pages_checked}"
    )

    print(
        f"Unique historical PDFs found: "
        f"{len(all_links)}"
    )

    return all_links


def download_pdf(
    url,
    folder,
    prefix,
):
    """
    Download one PDF using a stable filename.
    """

    ensure_directories()

    existing = existing_file_for_url(
        url,
        folder,
        prefix,
    )

    if existing:
        print(
            f"Already downloaded: "
            f"{existing}"
        )

        return existing

    filename = stable_filename(
        url,
        prefix,
    )

    filepath = os.path.join(
        folder,
        filename,
    )

    print(
        f"Downloading PDF: "
        f"{url}"
    )

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=60,
    )

    response.raise_for_status()

    content_type = (
        response.headers
        .get(
            "Content-Type",
            "",
        )
        .lower()
    )

    content = response.content

    if (
        "pdf" not in content_type
        and not content.startswith(
            b"%PDF"
        )
    ):
        print(
            f"Skipped non-PDF response: "
            f"{url}"
        )

        return None

    with open(
        filepath,
        "wb",
    ) as file:
        file.write(content)

    print(
        f"Saved: {filepath}"
    )

    return filepath


def scrape_archive(
    base_url,
    folder,
    prefix,
):
    """
    Crawl and download an entire LONAB archive.
    """

    ensure_directories()

    links = collect_historical_pdf_links(
        base_url
    )

    downloaded = []

    for index, url in enumerate(
        links,
        start=1,
    ):

        print(
            "\n"
            f"[{index}/{len(links)}]"
        )

        try:
            filepath = download_pdf(
                url,
                folder,
                prefix,
            )

            if filepath:
                downloaded.append(
                    filepath
                )

        except requests.HTTPError as error:

            print(
                f"{prefix.capitalize()} "
                f"download error: "
                f"{error}"
            )

        except Exception as error:

            print(
                f"{prefix.capitalize()} "
                f"unexpected download error: "
                f"{error}"
            )

    return downloaded


def scrape_programs():

    print(
        "\n"
        "SCRAPING PROGRAM ARCHIVE"
    )

    programs = scrape_archive(
        PROGRAM_URL,
        "data/raw/programs",
        "program",
    )

    print(
        "\n"
        "PROGRAM ARCHIVE COMPLETE"
    )

    print(
        f"Program PDFs processed: "
        f"{len(programs)}"
    )

    return programs


def scrape_results():

    print(
        "\n"
        "SCRAPING RESULT ARCHIVE"
    )

    results = scrape_archive(
        RESULTS_URL,
        "data/raw/results",
        "result",
    )

    print(
        "\n"
        "RESULT ARCHIVE COMPLETE"
    )

    print(
        f"Result PDFs processed: "
        f"{len(results)}"
    )

    return results


def run_scraper():

    print("=" * 60)
    print(
        "LONAB HISTORICAL RACE MACHINE SCRAPER"
    )
    print("=" * 60)

    print(
        "\n"
        f"Historical archive pages: "
        f"{HISTORICAL_PAGES}"
    )

    print(
        "\n"
        "SCRAPING PROGRAMS"
    )

    programs = scrape_programs()

    print(
        "\n"
        "SCRAPING RESULTS"
    )

    results = scrape_results()

    print(
        "\n"
        + "=" * 60
    )

    print(
        f"Program PDFs processed: "
        f"{len(programs)}"
    )

    print(
        f"Result PDFs processed: "
        f"{len(results)}"
    )

    print("=" * 60)

    return {
        "programs": programs,
        "results": results,
    }


if __name__ == "__main__":
    run_scraper()
