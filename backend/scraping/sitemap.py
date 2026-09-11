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
from bs4 import BeautifulSoup
from lxml import etree

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
MAX_FETCH_RETRIES = 1
DEFAULT_MAX_SITEMAPS = 30
DEFAULT_MAX_PAGE_URLS = 1000
MAX_SITEMAP_DOWNLOAD_BYTES = 6_000_000
MAX_SITEMAP_XML_BYTES = 8_000_000


def get_base_url(domain: str) -> str:
    """Ensure domain has scheme."""
    domain = domain.strip().rstrip("/")
    if not domain.startswith(("http://", "https://")):
        domain = "https://" + domain
    return domain


def fetch_url(url: str, timeout: int = 10, max_retries: int = MAX_FETCH_RETRIES) -> Optional[bytes]:
    """Fetch bounded sitemap/robots content without materializing huge bodies."""
    for attempt in range(max_retries + 1):
        try:
            with requests.get(
                url,
                headers=HEADERS,
                timeout=timeout,
                allow_redirects=True,
                stream=True,
            ) as resp:
                if resp.status_code == 429 or resp.status_code >= 500:
                    if attempt < max_retries:
                        time.sleep(0.75 * (2 ** attempt))
                        continue
                resp.raise_for_status()
                declared_size = int(resp.headers.get("content-length") or 0)
                if declared_size > MAX_SITEMAP_DOWNLOAD_BYTES:
                    logger.warning("Skipping oversized sitemap response %s (%s bytes)", url, declared_size)
                    return None
                content = bytearray()
                for chunk in resp.iter_content(chunk_size=64 * 1024):
                    content.extend(chunk)
                    if len(content) > MAX_SITEMAP_DOWNLOAD_BYTES:
                        logger.warning("Skipping sitemap response over byte limit: %s", url)
                        return None
                return bytes(content)
        except Exception as e:
            if attempt < max_retries:
                time.sleep(0.75 * (2 ** attempt))
                continue
            logger.debug(f"Fetch failed for {url}: {e}")
    return None


def decompress_if_gzip(content: bytes) -> bytes:
    """Decompress gzip with an output ceiling to prevent gzip memory bombs."""
    if content[:2] == b'\x1f\x8b':
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(content)) as stream:
                expanded = stream.read(MAX_SITEMAP_XML_BYTES + 1)
            if len(expanded) > MAX_SITEMAP_XML_BYTES:
                logger.warning("Skipping gzip sitemap over decompressed byte limit")
                return b""
            return expanded
        except Exception:
            return b""
    if len(content) > MAX_SITEMAP_XML_BYTES:
        logger.warning("Skipping sitemap XML over byte limit")
        return b""
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


def _bounded_sitemap_locations(content: bytes, max_locations: int) -> tuple[str, List[str]]:
    """Read only the needed XML locations while clearing parsed elements."""
    xml = decompress_if_gzip(content)
    if not xml or max_locations <= 0:
        return "", []
    kind = ""
    locations: List[str] = []
    try:
        for event, element in etree.iterparse(
            io.BytesIO(xml), events=("start", "end"), recover=True,
        ):
            local_name = element.tag.rsplit("}", 1)[-1] if isinstance(element.tag, str) else ""
            if event == "start" and not kind and local_name in {"urlset", "sitemapindex"}:
                kind = local_name
            elif event == "end" and local_name == "loc":
                value = (element.text or "").strip()
                if value:
                    locations.append(value)
                if len(locations) >= max_locations:
                    break
            if event == "end":
                element.clear()
        return kind, locations
    except (etree.XMLSyntaxError, ValueError) as exc:
        logger.warning("Streaming sitemap parse error: %s", exc)
        return "", []


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

        kind, urls = _bounded_sitemap_locations(
            content,
            max(1, (max_sitemaps or DEFAULT_MAX_SITEMAPS) - len(found_sitemaps)),
        )
        if not kind:
            return

        if kind == "sitemapindex":
            for child_url in urls:
                if max_sitemaps is not None and len(found_sitemaps) >= max_sitemaps:
                    break
                _walk_sitemap(child_url, depth + 1)
            return

        if kind == "urlset":
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
    if not found_sitemaps:
        for path in COMMON_SITEMAP_PATHS:
            sm_url = urljoin(base_url, path)
            _walk_sitemap(sm_url)
            if found_sitemaps:
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

    if len(all_page_urls) <= 1:
        logger.info("Sitemap coverage was empty for %s; crawling internal HTML links", domain)
        html_limit = min(max_urls or DEFAULT_MAX_PAGE_URLS, 100)
        html_urls = crawl_internal_html_links(base_url, timeout=timeout, max_urls=html_limit)
        all_page_urls.extend(html_urls)

    if not all_page_urls:
        all_page_urls.append(base_url)

    deduped_urls = list(dict.fromkeys(all_page_urls))
    return deduped_urls[:max_urls] if max_urls is not None else deduped_urls


def crawl_internal_html_links(base_url: str, timeout: int = 10, max_urls: int = 100) -> List[str]:
    """Bounded same-site crawl used when a site has no usable XML sitemap."""
    parsed_base = urlparse(base_url)
    allowed_host = parsed_base.netloc.lower().removeprefix("www.")
    pending: list[tuple[str, int]] = [(base_url, 0)]
    visited: set[str] = set()
    discovered: list[str] = []

    while pending and len(discovered) < max_urls:
        current_url, depth = pending.pop(0)
        normalized = current_url.split("#", 1)[0].rstrip("/") or base_url
        if normalized in visited:
            continue
        visited.add(normalized)
        try:
            response = requests.get(normalized, headers=HEADERS, timeout=timeout, allow_redirects=True)
            content_type = response.headers.get("content-type", "").lower()
            if response.status_code >= 400 or "text/html" not in content_type:
                continue
        except requests.RequestException:
            continue

        final_url = response.url.split("#", 1)[0]
        final_host = urlparse(final_url).netloc.lower().removeprefix("www.")
        if final_host != allowed_host:
            continue
        discovered.append(final_url)
        if depth >= 2:
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        for anchor in soup.select("a[href]"):
            candidate = urljoin(final_url, anchor.get("href", "")).split("#", 1)[0]
            parsed = urlparse(candidate)
            host = parsed.netloc.lower().removeprefix("www.")
            if parsed.scheme not in {"http", "https"} or host != allowed_host:
                continue
            if _looks_like_sitemap_url(candidate) or parsed.path.lower().endswith(
                (".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".zip", ".xml")
            ):
                continue
            candidate = candidate.rstrip("/") or base_url
            if candidate not in visited and all(item[0] != candidate for item in pending):
                pending.append((candidate, depth + 1))
                if len(pending) + len(discovered) >= max_urls * 2:
                    break

    return list(dict.fromkeys(discovered))[:max_urls]


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
    remaining = max_urls if max_urls is not None else DEFAULT_MAX_PAGE_URLS
    kind, urls = _bounded_sitemap_locations(content, max(1, remaining))

    if kind == "sitemapindex":
        page_urls: List[str] = []
        for child_url in urls:
            child_limit = None if max_urls is None else max(0, max_urls - len(page_urls))
            if child_limit == 0:
                break
            page_urls.extend(_collect_page_urls_from_sitemap(child_url, timeout, visited, depth + 1, child_limit))
            page_urls = list(dict.fromkeys(page_urls))
            if max_urls is not None and len(page_urls) >= max_urls:
                break
        return page_urls

    page_urls = [url for url in urls if not _looks_like_sitemap_url(url)] if kind == "urlset" else []
    return page_urls[:max_urls] if max_urls is not None else page_urls


def _looks_like_sitemap_url(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.lower()
    return path.endswith((".xml", ".xml.gz")) or "sitemap" in path
