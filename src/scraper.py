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
        path for path in glob.glob(
            os.path.join(folder, f"{prefix}_*_{url_hash(url)}.pdf")
        ) if os.path.isfile(path)
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
    # The current LONAB "Télécharger" anchor can contain only an icon. Walk up
    # only to the nearest article/card carrying the document title; never merge
    # the whole page because that would mix programme and results navigation.
    node = link
    fallback = ""
    for _ in range(7):
        if node is None:
            break
        context = _text(node.get_text(" ", strip=True))
        if context and not fallback:
            fallback = context
        if (
            "journal hippique" in context
            or "télécharger les résultats pmu" in context
            or "telecharger les resultats pmu" in context
            or "récapitulatif des arrivées" in context
            or "recapitulatif des arrivees" in context
        ):
            # Article/card contexts are small. A huge context is usually body
            # or a navigation wrapper containing unrelated documents.
            if len(context) <= 1500:
                return context
        node = node.parent
    return fallback


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
        ("résultat" in context or "resultat" in context or "arrivée" in context or "arrivee" in context)
        and "pmu" in context
    )


def _is_same_site(url, page_url):
    return (
        urlparse(url).netloc.lower().removeprefix("www.")