import os
import re
import glob
import hashlib
from urllib.parse import urljoin, urlparse, unquote

import requests
from bs4 import BeautifulSoup


# Official LONAB listing pages. Keep the compatibility fallbacks because the
# site has exposed both www and non-www routes.
PROGRAM_URLS = (
    "https://www.lonab.bf/programme-pmub",
    "https://lonab.bf/fr/programme-pmub",
    "https://www.lonab.bf/fr/programme-pmub",
)
RESULTS_URLS = (
    "https://www.lonab.bf/resultats-gains-pmub",
    "https://lonab.bf/fr/resultats-gains-pmub",
    "https://www.lonab.bf/fr/resultats-gains-ecd",
)

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
    return unquote(str(url).strip().split("#")[0])


def url_hash(url):
    return hashlib.md5(normalize_url(url).encode("utf-8")).hexdigest()[:10]


def safe_original_filename(url):
    name = unquote(os.path.basename(urlparse(url).path)) or "document.pdf"
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    name = re.sub(r"[^a-zA-Z0-9._-]", "_", name)
    return name[:100]


def stable_filename(url, prefix):
    stem, _ = os.path.splitext(safe_original_filename(url))
    return f"{prefix}_{stem}_{url_hash(url)}.pdf"


def existing_file_for_url(url, folder, prefix):
    exact = os.path.join(folder, stable_filename(url, prefix))
    if os.path.isfile(exact):
        return exact
    matches = sorted(
        path
        for path in glob.glob(
            os.path.join(folder, f"{prefix}_*_{url_hash(url)}.pdf")
        )
        if os.path.isfile(path)
    )
    return matches[0] if matches else None


def build_archive_page_urls(base_url):
    urls = []
    for page in range(HISTORICAL_PAGES):
        if page == 0:
            urls.append(base_url)
        else:
            separator = "&" if "?" in base_url else "?"
            urls.append(f"{base_url}{separator}page={page}")
    return urls


def _text(value):
    return re.sub(r"\s+", " ", value or "").strip().lower()


def _entry_context(link):
    # The current LONAB "Télécharger" anchor can contain only an icon. Its
    # article/card ancestor contains the real title, so classify the ancestor
    # rather than the anchor text itself.
    parts = []
    node = link
    for _ in range(7):
        if node is None:
            break
        parts.append(node.get_text(" ", strip=True))
        node = node.parent
    return _text(" ".join(parts))


def _matches_kind(context, kind):
    if kind == "program":
        return (
            "journal hippique" in context
            and "pmu" in context
            and "résultat" not in context
            and "resultat" not in context
            and "arrivée" not in context
            and "arrivee" not in context
            and " ecd " not in f" {context} "
        )
    return (
        (
            "résultat" in context
            or "resultat" in context
            or "arrivée" in context
            or "arrivee" in context
        )
        and "pmu" in context
    )


def _is_same_site(url, page_url):
    return (
        urlparse(url).netloc.lower().removeprefix("www.")
        == urlparse(page_url).netloc.lower().removeprefix("www.")
    )


def _pdf_urls_from_html(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    urls = []

    for tag in soup.find_all(True):
        for attribute in (
            "href",
            "src",
            "data-href",
            "data-url",
            "data-file",
            "data-download",
        ):
            value = tag.get(attribute)
            if value and ".pdf" in str(value).lower():
                url = normalize_url(urljoin(base_url, str(value).strip()))
                if url not in urls:
                    urls.append(url)

    for match in re.finditer(
        r'''["']([^"'<>\s]+\.pdf(?:\?[^"'<>\s]*)?)["']''',
        html,
        re.IGNORECASE,
    ):
        url = normalize_url(urljoin(base_url, match.group(1)))
        if url not in urls:
            urls.append(url)

    return urls


def _resolve_candidate(candidate_url):
    response = requests.get(
        candidate_url,
        headers=HEADERS,
        timeout=30,
        allow_redirects=True,
    )
    response.raise_for_status()

    content_type = response.headers.get("Content-Type", "").lower()
    content = response.content

    if "pdf" in content_type or content.startswith(b"%PDF"):
        return [normalize_url(response.url)]

    return _pdf_urls_from_html(response.text, response.url)


def get_pdf_links(page_url, kind):
    print(f"Checking {kind} archive page: {page_url}")

    response = requests.get(page_url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    candidates = []
    seen_candidates = set()

    for link in soup.find_all("a", href=True):
        href = str(link.get("href", "")).strip()
        if not href or href.startswith("#"):
            continue
        if href.lower().startswith(("javascript:", "mailto:", "tel:")):
            continue

        context = _entry_context(link)
        if not _matches_kind(context, kind):
            continue

        absolute = normalize_url(urljoin(page_url, href))
        if not _is_same_site(absolute, page_url):
            continue

        if absolute not in seen_candidates:
            seen_candidates.add(absolute)
            candidates.append(absolute)

    pdf_links = []
    seen_pdfs = set()

    for candidate in candidates:
        try:
            if urlparse(candidate).path.lower().endswith(".pdf"):
                resolved = [candidate]
            else:
                resolved = _resolve_candidate(candidate)

            for url in resolved:
                if url not in seen_pdfs:
                    seen_pdfs.add(url)
                    pdf_links.append(url)
        except Exception as error:
            print(f"Candidate skipped: {candidate} | {error}")

    return pdf_links


def collect_historical_pdf_links(base_url, kind):
    all_links = []
    seen = set()
    pages_checked = 0

    for page_url in build_archive_page_urls(base_url):
        try:
            links = get_pdf_links(page_url, kind)
            pages_checked += 1
            print(f"Qualified {kind} PDFs found on page: {len(links)}")

            for link in links:
                if link not in seen:
                    seen.add(link)
                    all_links.append(link)
        except Exception as error:
            print(f"Archive page error: {page_url}")
            print(f"Error: {error}")

    print(f"Archive pages checked: {pages_checked}")
    print(f"Unique qualified {kind} PDFs found: {len(all_links)}")
    return all_links


def download_pdf(url, folder, prefix):
    ensure_directories()

    existing = existing_file_for_url(url, folder, prefix)
    if existing:
        print(f"Already downloaded: {existing}")
        return existing

    print(f"Downloading PDF: {url}")
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=60,
        allow_redirects=True,
    )
    response.raise_for_status()

    content = response.content
    content_type = response.headers.get("Content-Type", "").lower()
    if "pdf" not in content_type and not content.startswith(b"%PDF"):
        print(f"Skipped non-PDF response: {url}")
        return None

    final_url = normalize_url(response.url)
    path = os.path.join(folder, stable_filename(final_url, prefix))
    with open(path, "wb") as file:
        file.write(content)

    print(f"Saved: {path}")
    return path


def scrape_archive(base_url, folder, prefix, kind):
    ensure_directories()
    links = collect_historical_pdf_links(base_url, kind)
    downloaded = []

    for index, url in enumerate(links, start=1):
        print(f"\n[{index}/{len(links)}]")
        try:
            path = download_pdf(url, folder, prefix)
            if path:
                downloaded.append(path)
        except Exception as error:
            print(f"{prefix.capitalize()} download error: {error}")

    return downloaded


def scrape_sources(base_urls, folder, prefix, label):
    merged = []
    seen = set()

    for base_url in base_urls:
        print("\n" + "-" * 60)
        print(f"Trying {label} source: {base_url}")
        print("-" * 60)

        try:
            paths = scrape_archive(base_url, folder, prefix, label)
        except Exception as error:
            print(f"{label.capitalize()} source failed: {base_url}")
            print(f"Error: {error}")
            continue

        for path in paths:
            if path and path not in seen:
                seen.add(path)
                merged.append(path)

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
    print("LONAB RACE MACHINE SCRAPER")
    print("=" * 60)
    print(f"\nHistorical archive pages: {HISTORICAL_PAGES}")

    print("\nSCRAPING PROGRAMS")
    programs = scrape_programs()

    print("\nSCRAPING RESULTS")
    results = scrape_results()

    print("\n" + "=" * 60)
    print(f"Program PDFs processed: {len(programs)}")
    print(f"Result PDFs processed: {len(results)}")
    print("=" * 60)

    return {"programs": programs, "results": results}


if __name__ == "__main__":
    run_scraper()
