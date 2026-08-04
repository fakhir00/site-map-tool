import logging
from typing import List, Dict, Any, Optional
from apify_client import ApifyClient
from app.config import settings
from scraping.crawler import ScrapedPage
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

def is_apify_configured() -> bool:
    return bool(settings.APIFY_API_TOKEN)

def _get_client() -> ApifyClient:
    return ApifyClient(settings.APIFY_API_TOKEN)

def search_google_via_apify(query: str, max_results: int = 10) -> List[Dict[str, Any]]:
    """
    Search Google using Apify's google-search-scraper.
    Returns structured organic results.
    """
    if not is_apify_configured():
        logger.warning("Apify not configured. Skipping Google search via Apify.")
        return []

    client = _get_client()
    run_input = {
        "queries": query,
        "maxPagesPerQuery": 1,
        "resultsPerPage": max_results,
        "countryCode": "us",
        "languageCode": "en",
    }
    
    try:
        logger.info(f"Running Apify google-search-scraper for query: {query}")
        run = client.actor("apify/google-search-scraper").call(run_input=run_input)
        
        results = []
        for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            if "organicResults" in item:
                for organic_item in item["organicResults"]:
                    results.append({
                        "url": organic_item.get("url"),
                        "title": organic_item.get("title"),
                        "snippet": organic_item.get("description")
                    })
        return results[:max_results]
    except Exception as exc:
        logger.error(f"Apify search failed for {query}: {exc}")
        return []

def crawl_competitor_content_via_apify(domain_or_url: str, max_pages: int = 5) -> List[str]:
    """
    Crawl a competitor using website-content-crawler.
    Returns list of urls that were crawled. The actual page scraping result can be extracted here or we just return URLs.
    Wait, pipeline.py's _discover_content_urls expects a list of URLs.
    Let's return a list of discovered and scraped URLs.
    """
    if not is_apify_configured():
        return []

    client = _get_client()
    run_input = {
        "startUrls": [{"url": domain_or_url}],
        "crawlerType": "playwright:adaptive",
        "maxRequestsPerCrawl": max_pages,
        "proxyConfiguration": {"useApifyProxy": True},
    }
    
    try:
        logger.info(f"Running Apify website-content-crawler for: {domain_or_url}")
        run = client.actor("apify/website-content-crawler").call(run_input=run_input)
        
        urls = []
        for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            url = item.get("url")
            if url:
                urls.append(url)
        return urls
    except Exception as exc:
        logger.error(f"Apify crawler failed for {domain_or_url}: {exc}")
        return []

def extract_apify_page_content(url: str) -> Optional[ScrapedPage]:
    """
    Extract content from a single URL using Apify, returning a ScrapedPage object.
    Useful for fallback if requests-based crawler gets blocked.
    """
    if not is_apify_configured():
        return None

    client = _get_client()
    run_input = {
        "startUrls": [{"url": url}],
        "crawlerType": "playwright:adaptive",
        "maxRequestsPerCrawl": 1,
    }
    
    try:
        run = client.actor("apify/website-content-crawler").call(run_input=run_input)
        
        for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            if item.get("url") == url or url in item.get("url", ""):
                text = item.get("text", "")
                word_count = len(text.split()) if text else 0
                title = item.get("metadata", {}).get("title", "")
                # We can't easily get H2/H3 counts from text but it gives us the clean text
                return ScrapedPage(
                    url=item.get("url", url),
                    h1=title,
                    text=text,
                    word_count=word_count,
                    status_code=200,
                )
        return None
    except Exception as exc:
        logger.error(f"Apify single-page extraction failed for {url}: {exc}")
        return None
