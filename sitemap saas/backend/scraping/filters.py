"""
URL filtering: keeps only blog-like content URLs based on pattern matching.
"""

import re
from typing import List
from urllib.parse import urlparse


# Default blog-like path patterns
DEFAULT_BLOG_PATTERNS = [
    r"/blog/",
    r"/news/",
    r"/post/",
    r"/posts/",
    r"/article/",
    r"/articles/",
    r"/insights/",
    r"/resources/",
    r"/guides/",
    r"/tutorials?/",
    r"/stories/",
    r"/updates/",
    r"/press/",
    r"/media/",
    r"/learn/",
    r"/knowledge/",
    r"/support/",
    # Date patterns like /2023/, /2024/01/
    r"/\d{4}/\d{2}/",
    r"/\d{4}/\d{2}/\d{2}/",
    r"/\d{4}/",
]

# Paths to always exclude
EXCLUDE_PATTERNS = [
    r"\.(jpg|jpeg|png|gif|svg|webp|ico|pdf|zip|gz|tar|mp4|mp3|css|js)(\?|$)",
    r"/tag/",
    r"/tags/",
    r"/category/",
    r"/categories/",
    r"/author/",
    r"/authors/",
    r"/page/\d+",
    r"/wp-json/",
    r"/wp-admin/",
    r"/wp-content/",
    r"/feed/",
    r"/rss/",
    r"/amp/",
    r"#",
    r"\?s=",
    r"/search/",
    r"/cart/",
    r"/checkout/",
    r"/account/",
    r"/login/",
    r"/register/",
    r"/sitemap",
]


def is_blog_url(url: str, patterns: List[str] = None) -> bool:
    """Check if a URL looks like a blog/content post."""
    if not url or not url.startswith(("http://", "https://")):
        return False

    parsed = urlparse(url)
    path = parsed.path.lower()

    # Check exclusions first
    for exc in EXCLUDE_PATTERNS:
        if re.search(exc, url, re.IGNORECASE):
            return False

    # Use provided patterns or defaults
    check_patterns = patterns or DEFAULT_BLOG_PATTERNS
    for pat in check_patterns:
        if re.search(pat, path, re.IGNORECASE):
            return True

    # Heuristic: path with 2+ segments and a slug-like final segment
    segments = [s for s in path.split("/") if s]
    if len(segments) >= 2:
        last = segments[-1]
        # Slug-like: contains hyphens, at least 15 chars, looks like a title
        if len(last) > 15 and "-" in last and not last.endswith((".html", ".php")):
            return True
        # .html or .php pages with meaningful slug
        if last.endswith((".html", ".php")) and len(last) > 20 and "-" in last:
            return True

    return False


def filter_blog_urls(urls: List[str], patterns: List[str] = None, domain: str = None) -> List[str]:
    """Filter a list of URLs to only blog-like content URLs."""
    filtered = []
    seen = set()

    for url in urls:
        url = url.strip()
        if not url or url in seen:
            continue
        seen.add(url)

        # Optionally restrict to same domain
        if domain:
            try:
                parsed = urlparse(url)
                domain_parsed = urlparse(domain)
                if parsed.netloc and parsed.netloc != domain_parsed.netloc:
                    # Allow subdomains of the same root domain
                    if not parsed.netloc.endswith("." + domain_parsed.netloc):
                        continue
            except Exception:
                pass

        if is_blog_url(url, patterns):
            filtered.append(url)

    return filtered


def get_url_slug(url: str) -> str:
    """Extract slug from URL for display."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    return path.split("/")[-1] if path else url
