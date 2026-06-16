"""
Sitemap discovery: finds all sitemap URLs for a given domain.
Handles:
  - /sitemap.xml
  - /sitemap_index.xml
  - robots.txt Sitemap directive
  - Gzipped sitemaps (.gz)
  - Nested sitemap index files
"""

import gzip
import re
import io
import logging
import time
from typing import List, Optional
from urllib.parse import urljoin, urlparse
import requests
import xmltodict

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "SiteMapSEO/1.0 (SEO analysis bot; +https://sitemapseo.io/bot)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate",
}

COMMON_SITEMAP_PATHS = [
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/sitemap/sitemap.xml",
    "/sitemap/",
    "/sitemaps/sitemap.xml",
    "/news-sitemap.xml",
    "/blog-sitemap.xml",
    "/post-sitemap.xml",
]

MAX_SITEMAP_DEPTH = 6
MAX_FETCH_RETRIES = 2
DEFAULT_MAX_SITEMAPS = 30
DEFAULT_MAX_PAGE_URLS = 1000


def get_base_url(domain: str) -> str:
    """Ensure domain has scheme."""
    domain = domain.strip().rstrip("/")
    if not domain.startswith(("http://", "https://")):
        domain = "https://" + domain
    return domain


def fetch_url(url: str, timeout: int = 10, max_retries: int = MAX_FETCH_RETRIES) -> Optional[bytes]:
    """Fetch URL content, returns bytes or None on failure."""
    for attempt in range(max_retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt < max_retries:
                    time.sleep(0.75 * (2 ** attempt))
                    continue
            resp.raise_for_status()
            return resp.content
        except Exception as e:
            if attempt < max_retries:
                time.sleep(0.75 * (2 ** attempt))
                continue
            logger.debug(f"Fetch failed for {url}: {e}")
    return None


def decompress_if_gzip(content: bytes) -> bytes:
    """Decompress gzipped content if needed."""
    if content[:2] == b'\x1f\x8b':
        try:
            return gzip.decompress(content)
        except Exception:
            pass
    return content


def parse_sitemap_xml(content: bytes) -> dict:
    """Parse XML sitemap to dict."""
    try:
        text = decompress_if_gzip(content).decode("utf-8", errors="replace")
        return xmltodict.parse(text.strip())
    except Exception as e:
        logger.warning(f"XML parse error: {e}")
        return {}


def extract_urls_from_sitemap(data: dict) -> List[str]:
    """Extract URLs from parsed sitemap dict (handles urlset and sitemapindex)."""
    urls = []

    # URL set (regular sitemap)
    urlset = data.get("urlset", {})
    if urlset:
        url_entries = urlset.get("url", [])
        if isinstance(url_entries, dict):
            url_entries = [url_entries]
        for entry in url_entries:
            loc = entry.get("loc")
            if loc:
                urls.append(loc.strip())

    # Sitemap index (nested)
    sitemapindex = data.get("sitemapindex", {})
    if sitemapindex:
        sitemap_entries = sitemapindex.get("sitemap", [])
        if isinstance(sitemap_entries, dict):
            sitemap_entries = [sitemap_entries]
        for entry in sitemap_entries:
            loc = entry.get("loc")
            if loc:
                urls.append(loc.strip())

    return urls


def parse_robots_txt(content: bytes, base_url: str) -> List[str]:
    """Extract Sitemap directives from robots.txt."""
    sitemaps = []
    text = content.decode("utf-8", errors="replace")
    for line in text.splitlines():
        line = line.strip()
        if line.lower().startswith("sitemap:"):
            sitemap_url = line.split(":", 1)[1].strip()
            sitemaps.append(sitemap_url)
    return sitemaps


def discover_sitemaps(
    domain: str,
    timeout: int = 10,
    max_sitemaps: int | None = DEFAULT_MAX_SITEMAPS,
) -> List[str]:
    """
    Discover all sitemap URLs for a domain.
    Returns list of sitemap XML URLs.
    """
    base_url = get_base_url(domain)
    found_sitemaps: List[str] = []
    visited: set = set()

    def _walk_sitemap(url: str, depth: int = 0) -> None:
        """Fetch and parse sitemap indexes recursively."""
        if url in visited or depth > MAX_SITEMAP_DEPTH:
            return
        if max_sitemaps is not None and len(found_sitemaps) >= max_sitemaps:
            return
        visited.add(url)

        content = fetch_url(url, timeout)
        if not content:
            return

        data = parse_sitemap_xml(content)
        if not data:
            return

        if "sitemapindex" in data:
            for child_url in extract_urls_from_sitemap(data):
                if max_sitemaps is not None and len(found_sitemaps) >= max_sitemaps:
                    break
                _walk_sitemap(child_url, depth + 1)
            return

        if "urlset" in data:
            found_sitemaps.append(url)

    # 1. Try robots.txt
    robots_url = urljoin(base_url, "/robots.txt")
    robots_content = fetch_url(robots_url, timeout)
    if robots_content:
        robots_sitemaps = parse_robots_txt(robots_content, base_url)
        for sm_url in robots_sitemaps:
            _walk_sitemap(sm_url)
            if max_sitemaps is not None and len(found_sitemaps) >= max_sitemaps:
                break

    # 2. Try common sitemap paths
    for path in COMMON_SITEMAP_PATHS:
        sm_url = urljoin(base_url, path)
        _walk_sitemap(sm_url)
        if max_sitemaps is not None and len(found_sitemaps) >= max_sitemaps:
            break

    # Deduplicate
    return list(dict.fromkeys(found_sitemaps))


def extract_all_urls_from_domain(
    domain: str,
    timeout: int = 10,
    max_urls: int | None = DEFAULT_MAX_PAGE_URLS,
) -> List[str]:
    """
    Full URL extraction: discover sitemaps + extract all page URLs.
    Returns flat list of all URLs found in all sitemaps.
    """
    base_url = get_base_url(domain)
    sitemap_cap = None if max_urls is None else max(5, min(DEFAULT_MAX_SITEMAPS, max_urls // 25 or 1))
    sitemap_urls = discover_sitemaps(domain, timeout, max_sitemaps=sitemap_cap)

    if not sitemap_urls:
        logger.info(f"No sitemaps found for {domain}, trying direct /sitemap.xml parse")
        # Last resort: try parsing /sitemap.xml directly for URLs
        sitemap_urls = [urljoin(base_url, "/sitemap.xml")]

    all_page_urls: List[str] = []
    visited: set = set()

    for sm_url in sitemap_urls:
        all_page_urls.extend(_collect_page_urls_from_sitemap(sm_url, timeout, visited, max_urls=max_urls))
        all_page_urls = list(dict.fromkeys(all_page_urls))
        if max_urls is not None and len(all_page_urls) >= max_urls:
            break

    if not all_page_urls:
        logger.info(f"Fallback: returning base URL {base_url} as sitemap discovery failed")
        all_page_urls.append(base_url)

    deduped_urls = list(dict.fromkeys(all_page_urls))
    return deduped_urls[:max_urls] if max_urls is not None else deduped_urls


def _collect_page_urls_from_sitemap(
    sitemap_url: str,
    timeout: int,
    visited: set,
    depth: int = 0,
    max_urls: int | None = None,
) -> List[str]:
    """Collect page URLs from URL sitemaps and nested sitemap indexes."""
    if sitemap_url in visited or depth > MAX_SITEMAP_DEPTH:
        return []
    visited.add(sitemap_url)

    content = fetch_url(sitemap_url, timeout)
    if not content:
        return []
    data = parse_sitemap_xml(content)
    urls = extract_urls_from_sitemap(data)

    if "sitemapindex" in data:
        page_urls: List[str] = []
        for child_url in urls:
            page_urls.extend(_collect_page_urls_from_sitemap(child_url, timeout, visited, depth + 1, max_urls))
            page_urls = list(dict.fromkeys(page_urls))
            if max_urls is not None and len(page_urls) >= max_urls:
                break
        return page_urls

    page_urls = [url for url in urls if not _looks_like_sitemap_url(url)]
    return page_urls[:max_urls] if max_urls is not None else page_urls


def _looks_like_sitemap_url(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.lower()
    return path.endswith((".xml", ".xml.gz")) or "sitemap" in path
