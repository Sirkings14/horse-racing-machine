import os
import re
import glob
import hashlib
from urllib.parse import urljoin, urlparse, unquote

import requests
from bs4 import BeautifulSoup


# Canonical LONAB endpoints plus compatibility fallbacks. LONAB has exposed
# both www and non-www URLs over time, and a failed/empty first endpoint must
# never make the machine conclude that there is no race program.
PROGRAM_URLS = (
    "https://www.lonab.bf/programme-pmub",
    "https://lonab.bf/fr/programme-pmub",
    "https://www.lonab.bf/fr/programme-pmub",
)
RESULTS_URLS = (
    "https://www.lonab.bf/resultats-gains-ecd",
    "https://lonab.bf/fr/resultats-gains-ecd",
    "https://www.lonab.bf/fr/resultats-gains-ecd",
)

# Number of archive pages to inspect.
# Daily autonomous runs should stay fast and prioritize the newest pages.
# Use HISTORICAL_PAGES=250 only for an intentional one-off historical backfill.
HISTORICAL_PAGES = int(os.getenv("HISTORICAL_PAGES", "5"))

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
    url = url.strip()
    url = url.split("#")[0]
    return unquote(url)


def url_hash(url):
    normalized = normalize_url(url)

    return hashlib.md5(
        normalized.encode("utf-8")
    ).hexdigest()[:10]


def safe_original_filename(url):
    parsed = urlparse(url)

    original_name = os.path.basename(
        parsed.path
    )

    if not original_name:
        original_name = "document.pdf"

    original_name = unquote(original_name)

    if not original_name.lower().endswith(".pdf"):
        original_name += ".pdf"

    original_name = re.sub(
        r"[^a-zA-Z0-9._-]",
        "_",
        original_name
    )

    if len(original_name) > 100:
        original_name = original_name[:96] + ".pdf"

    return original_name


def stable_filename(url, prefix):
    original_name = safe_original_filename(url)

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
    prefix
):
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

    old_pattern = os.path.join(
        folder,
        f"{prefix}_*_{source_hash}.pdf"
    )

    matches = glob.glob(old_pattern)

    matches = [
        path
        for path in matches
        if os.path.isfile(path)
    ]

    matches.sort()

    if matches:
        return matches[0]

    return None


def build_archive_page_urls(base_url):
    urls = []

    for page in range(HISTORICAL_PAGES):
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


def extract_pdf_links_from_soup(soup, page_url):
    links = []

    for link in soup.find_all("a", href=True):
        href = link.get("href", "").strip()
        if not href or href.startswith("#"):
            continue

        absolute_url = normalize_url(urljoin(page_url, href))
        parsed = urlparse(absolute_url)

        if parsed.path.lower().endswith(".pdf") and absolute_url not in links:
            links.append(absolute_url)

    return links


def get_pdf_links(page_url):
    print(f"Checking archive page: {page_url}")

    response = requests.get(
        page_url,
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    pdf_links = extract_pdf_links_from_soup(soup, page_url)

    # Some LONAB listing pages link first to an article/detail page rather than
    # directly to the PDF. Follow likely journal/result detail links one level
    # and extract the real PDF from there. This prevents a fresh daily program
    # from being missed simply because the listing HTML changed shape.
    detail_urls = []

    for link in soup.find_all("a", href=True):
        href = link.get("href", "").strip()
        label = " ".join(
            filter(
                None,
                [
                    link.get_text(" ", strip=True),
                    link.get("title", ""),
                    link.get("aria-label", ""),
                    href,
                ],
            )
        ).upper()

        # Newer LONAB listing cards sometimes keep the article title in a
        # surrounding element while the anchor itself only contains an icon.
        # Accept either recognizable label text OR a recognizable URL.
        if not any(
            token in label
            for token in (
                "JOURNAL HIPPIQUE",
                "PMU'B",
                "PMU’B",
                "PMUB",
                "RESULTAT",
                "RÉSULTAT",
                "TELECHARGER",
                "TÉLÉCHARGER",
                "PROGRAMME",
                "PROGRAM",
            )
        ):
            continue

        
        if not href or href.startswith("#"):
            continue

        detail_url = normalize_url(urljoin(page_url, href))
        if detail_url.lower().endswith(".pdf"):
            continue

        # LONAB serves the same site through both lonab.bf and www.lonab.bf.
        # Treat those aliases as one source instead of rejecting a valid detail
        # page just because the hostname spelling differs.
        detail_host = urlparse(detail_url).netloc.lower().removeprefix("www.")
        page_host = urlparse(page_url).netloc.lower().removeprefix("www.")
        if detail_host != page_host:
            continue

        if detail_url not in detail_urls:
            detail_urls.append(detail_url)

    for detail_url in detail_urls[:50]:
        try:
            detail_response = requests.get(
                detail_url,
                headers=HEADERS,
                timeout=30,
            )
            detail_response.raise_for_status()

            detail_soup = BeautifulSoup(
                detail_response.text,
                "html.parser",
            )

            for pdf_url in extract_pdf_links_from_soup(
                detail_soup,
                detail_url,
            ):
                if pdf_url not in pdf_links:
                    pdf_links.append(pdf_url)

        except Exception as error:
            print(
                f"Detail page skipped: {detail_url} | {error}"
            )

    # LONAB/Drupal pages sometimes expose documents through media attributes,
    # buttons, iframes, or inline JSON instead of a normal anchor.
    for tag in soup.find_all(True):
        for attribute in ("href", "src", "data-href", "data-url", "data-file", "data-download"):
            value = tag.get(attribute)
            if not value:
                continue
            value = str(value).strip()
            if ".pdf" not in value.lower():
                continue
            pdf_url = normalize_url(urljoin(page_url, value))
            if pdf_url not in pdf_links:
                pdf_links.append(pdf_url)

    # Scan the HTML for PDF paths as a final fallback.
    for match in re.finditer(
        r'''["']([^"'<>\s]+\.pdf(?:\?[^"'<>\s]*)?)["']''',
        response.text,
        re.IGNORECASE,
    ):
        pdf_url = normalize_url(urljoin(page_url, match.group(1)))
        if pdf_url not in pdf_links:
            pdf_links.append(pdf_url)

    return pdf_links


def collect_historical_pdf_links(base_url):
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

                seen.add(normalized)
                all_links.append(normalized)

                new_links += 1

            print(
                f"New unique PDFs: "
                f"{new_links}"
            )

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

    # The newest LONAB programs are often published before the race date.
    # Never stop after one empty archive page because a temporary rendering
    # issue can otherwise hide today's/tomorrow's program.
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
    prefix
):
    ensure_directories()

    existing = existing_file_for_url(
        url,
        folder,
        prefix
    )

    if existing:
        print(
            f"Already downloaded: "
            f"{existing}"
        )

        return existing

    filename = stable_filename(
        url,
        prefix
    )

    filepath = os.path.join(
        folder,
        filename
    )

    print(
        f"Downloading PDF: "
        f"{url}"
    )

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=60
    )

    response.raise_for_status()

    content_type = (
        response.headers
        .get(
            "Content-Type",
            ""
        )
        .lower()
    )

    content = response.content

    if (
        "pdf" not in content_type
        and not content.startswith(b"%PDF")
    ):
        print(
            f"Skipped non-PDF response: "
            f"{url}"
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


def scrape_archive(
    base_url,
    folder,
    prefix
):
    ensure_directories()

    links = collect_historical_pdf_links(
        base_url
    )

    downloaded = []

    for index, url in enumerate(
        links,
        start=1
    ):
        print(
            "\n"
            f"[{index}/{len(links)}]"
        )

        try:
            filepath = download_pdf(
                url,
                folder,
                prefix
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


def scrape_sources(base_urls, folder, prefix, label):
    """
    Try all known LONAB endpoints and merge unique downloaded PDFs.

    One endpoint may temporarily be empty or unavailable while another
    canonical URL already exposes the current program/results PDF.
    """
    merged = []
    seen = set()

    for base_url in base_urls:
        print("\n" + "-" * 60)
        print(f"Trying {label} source: {base_url}")
        print("-" * 60)

        try:
            paths = scrape_archive(base_url, folder, prefix)
        except Exception as error:
            print(f"{label.capitalize()} source failed: {base_url}")
            print(f"Error: {error}")
            continue

        for path in paths:
            if path and path not in seen:
                seen.add(path)
                merged.append(path)

        if not paths:
            print(
                f"{label.capitalize()} source produced no PDFs; "
                "continuing with fallback source."
            )

    return merged


def scrape_programs():
    print("\nSCRAPING PROGRAM ARCHIVE")

    programs = scrape_sources(
        PROGRAM_URLS,
        "data/raw/programs",
        "program",
        "program",
    )

    print("\nPROGRAM ARCHIVE COMPLETE")
    print(f"Program PDFs processed: {len(programs)}")

    return programs


def scrape_results():
    print("\nSCRAPING RESULT ARCHIVE")

    results = scrape_sources(
        RESULTS_URLS,
        "data/raw/results",
        "result",
        "result",
    )

    print("\nRESULT ARCHIVE COMPLETE")
    print(f"Result PDFs processed: {len(results)}")

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
        "results": results
    }


if __name__ == "__main__":
    run_scraper()
