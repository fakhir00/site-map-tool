"""
Content scraper: fetches HTML and extracts structured content from pages.
Handles: politeness delays, retries, robots.txt compliance, text extraction.
"""

import time
import random
import logging
import re
from datetime import date
from typing import Optional, Tuple
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "SiteMapSEO/1.0 (SEO analysis; +https://sitemapseo.io/bot)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "DNT": "1",
    "Connection": "keep-alive",
}

# Robots parser cache
_robots_cache: dict = {}


def get_robots_parser(domain: str) -> Optional[RobotFileParser]:
    """Get or create cached robots parser for a domain."""
    if domain in _robots_cache:
        return _robots_cache[domain]
    try:
        parsed = urlparse(domain)
        base = f"{parsed.scheme}://{parsed.netloc}"
        robots_url = f"{base}/robots.txt"
        rp = RobotFileParser()
        rp.set_url(robots_url)
        response = requests.get(robots_url, headers=HEADERS, timeout=5, allow_redirects=True)
        if response.status_code >= 400:
            _robots_cache[domain] = None
            return None
        rp.parse(response.text.splitlines())
        _robots_cache[domain] = rp
        return rp
    except Exception:
        _robots_cache[domain] = None
        return None


def can_fetch(url: str) -> bool:
    """Check if our bot is allowed to fetch this URL."""
    parsed = urlparse(url)
    domain = f"{parsed.scheme}://{parsed.netloc}"
    rp = get_robots_parser(domain)
    if rp is None:
        return True
    return rp.can_fetch("SiteMapSEO", url)


def extract_publish_date(soup: BeautifulSoup) -> Optional[date]:
    """Try to extract publish date from meta tags, schema, or URL."""
    # Try <meta property="article:published_time">
    for meta in soup.find_all("meta"):
        prop = meta.get("property", "") or meta.get("name", "")
        if "published" in prop.lower() or "date" in prop.lower():
            content = meta.get("content", "")
            if content:
                try:
                    from dateutil.parser import parse as parse_date
                    return parse_date(content).date()
                except Exception:
                    pass

    # Try JSON-LD schema
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            import json
            data = json.loads(script.string or "")
            if isinstance(data, dict):
                for key in ("datePublished", "dateCreated", "dateModified"):
                    if key in data:
                        from dateutil.parser import parse as parse_date
                        return parse_date(data[key]).date()
        except Exception:
            pass

    # Try <time> element
    for time_el in soup.find_all("time"):
        dt = time_el.get("datetime", "")
        if dt:
            try:
                from dateutil.parser import parse as parse_date
                return parse_date(dt).date()
            except Exception:
                pass

    return None


def extract_main_text(soup: BeautifulSoup) -> str:
    """Extract main article text using heuristics."""
    # Try trafilatura first
    try:
        import trafilatura
        html_str = str(soup)
        text = trafilatura.extract(html_str, include_comments=False, include_tables=False)
        if text and len(text) > 200:
            return text
    except Exception:
        pass

    # Fallback: find main content container
    for selector in ["article", "main", "[role='main']", ".post-content",
                     ".entry-content", ".article-content", ".blog-content",
                     "#content", ".content"]:
        el = soup.select_one(selector)
        if el:
            # Remove nav, aside, header, footer
            for tag in el.find_all(["nav", "aside", "header", "footer", "script", "style"]):
                tag.decompose()
            text = el.get_text(separator=" ", strip=True)
            if len(text) > 200:
                return text

    # Last resort: body text
    body = soup.find("body")
    if body:
        for tag in body.find_all(["script", "style", "nav", "header", "footer"]):
            tag.decompose()
        return body.get_text(separator=" ", strip=True)

    return ""


def count_words(text: str) -> int:
    """Count words in text."""
    return len(text.split()) if text else 0


def compute_readability(text: str) -> float:
    """Compute Flesch Reading Ease score."""
    try:
        import textstat
        return textstat.flesch_reading_ease(text)
    except Exception:
        return 0.0


class ScrapedPage:
    """Result of scraping a single page."""
    def __init__(
        self,
        url: str,
        h1: Optional[str] = None,
        h2s: Optional[list] = None,
        h3s: Optional[list] = None,
        text: str = "",
        word_count: int = 0,
        readability_score: float = 0.0,
        publish_date: Optional[date] = None,
        internal_links: int = 0,
        status_code: int = 200,
        error: Optional[str] = None,
    ):
        self.url = url
        self.h1 = h1
        self.h2s = h2s or []
        self.h3s = h3s or []
        self.text = text
        self.word_count = word_count
        self.readability_score = readability_score
        self.publish_date = publish_date
        self.internal_links = internal_links
        self.status_code = status_code
        self.error = error


def scrape_page(
    url: str,
    delay_min: float = 1.0,
    delay_max: float = 3.0,
    timeout: int = 15,
    max_retries: int = 2,
) -> ScrapedPage:
    """
    Fetch and parse a single URL.
    Respects robots.txt, applies random delay, retries on failure.
    """
    # Respect robots.txt
    if not can_fetch(url):
        return ScrapedPage(url=url, error="Blocked by robots.txt", status_code=403)

    # Politeness delay
    delay = random.uniform(delay_min, delay_max)
    time.sleep(delay)

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            if attempt > 0:
                time.sleep(random.uniform(2.0, 5.0))

            resp = requests.get(
                url,
                headers=HEADERS,
                timeout=timeout,
                allow_redirects=True,
            )

            if resp.status_code == 429:
                time.sleep(10)
                continue

            if resp.status_code == 403:
                # Try generic User-Agent
                fallback_headers = HEADERS.copy()
                fallback_headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
                resp = requests.get(
                    url,
                    headers=fallback_headers,
                    timeout=timeout,
                    allow_redirects=True,
                )
                if resp.status_code == 403:
                    return ScrapedPage(url=url, error="HTTP 403 Forbidden", status_code=403)

            if resp.status_code >= 400:
                return ScrapedPage(url=url, error=f"HTTP {resp.status_code}", status_code=resp.status_code)

            # Parse HTML
            soup = BeautifulSoup(resp.content, "lxml")

            # Remove noise
            for tag in soup.find_all(["script", "style", "noscript", "iframe", "svg"]):
                tag.decompose()

            # Extract H1
            h1_el = soup.find("h1")
            h1 = h1_el.get_text(strip=True) if h1_el else None
            title_el = soup.find("title")
            title = title_el.get_text(strip=True) if title_el else None
            if not h1 and title:
                h1 = title

            # Extract H2s/H3s
            h2s = [el.get_text(strip=True) for el in soup.find_all("h2")][:10]
            h3s = [el.get_text(strip=True) for el in soup.find_all("h3")][:10]

            # Extract main text
            text = extract_main_text(soup)

            # Metadata
            word_count = count_words(text)
            readability = compute_readability(text)
            publish_date = extract_publish_date(soup)

            # Count internal links
            parsed_url = urlparse(url)
            base_domain = parsed_url.netloc
            internal_links = 0
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"]
                if href.startswith("/") or base_domain in href:
                    internal_links += 1

            return ScrapedPage(
                url=url,
                h1=h1,
                h2s=h2s,
                h3s=h3s,
                text=text,
                word_count=word_count,
                readability_score=readability,
                publish_date=publish_date,
                internal_links=internal_links,
                status_code=resp.status_code,
            )

        except requests.Timeout:
            last_error = "Request timeout"
        except requests.ConnectionError:
            last_error = "Connection error"
        except Exception as e:
            last_error = str(e)[:200]
            logger.warning(f"Scrape error for {url}: {e}")

    return ScrapedPage(url=url, error=last_error or "Unknown error", status_code=0)
