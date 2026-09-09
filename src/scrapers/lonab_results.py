import hashlib
import re
from urllib.parse import urlparse


def safe_filename(url, prefix="result"):
    """
    Creates a short, filesystem-safe filename.
    Never uses full webpage text as a filename.
    """

    parsed = urlparse(url)

    original_name = parsed.path.split("/")[-1]

    if original_name:
        original_name = re.sub(r"[^a-zA-Z0-9._-]", "_", original_name)

        if len(original_name) <= 100:
            return original_name

    url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()[:12]

    return f"{prefix}_{url_hash}.pdf"
