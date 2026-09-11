import logging
from typing import List, Dict, Any, Optional
from apify_client import ApifyClient
from app.config import settings
from scraping.crawler import ScrapedPage

logger = logging.getLogger(__name__)

def is_apify_configured() -> bool:
    return bool(settings.APIFY_API_TOKEN)

def _get_client() -> ApifyClient:
    return ApifyClient(settings.APIFY_API_TOKEN)

def search_google_via_apify(query: str, max_results: int = 10, country_code: str = "us") -> List[Dict[str, Any]]:
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
        "countryCode": country_code.lower(),
        "languageCode": "en",
    }
    
    try:
        logger.info(f"Running Apify google-search-scraper for query: {query}")
        run = client.actor("apify/google-search-scraper").call(
            run_input=run_input,
            timeout_secs=90,
            wait_secs=100,
        )
        if not run or run.get("status") != "SUCCEEDED":
            return []
        
        results = []
        for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            organic_results = item.get("organicResults", [])
            for res in organic_results:
                url = res.get("url")
                if url and not url.startswith("https://apify.com/pricing"):
                    results.append({
                        "url": url,
                        "title": res.get("title"),
                        "snippet": res.get("description") or res.get("snippet")
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
        "maxCrawlPages": max_pages,
        "maxCrawlDepth": 1,
        "maxRequestsPerCrawl": max_pages,
        "proxyConfiguration": {"useApifyProxy": True},
    }
    
    try:
        logger.info(f"Running Apify website-content-crawler for: {domain_or_url}")
        run = client.actor("apify/website-content-crawler").call(
            run_input=run_input,
            timeout_secs=90,
            wait_secs=100,
        )
        if not run:
            return []
        
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
    
    # Use cheerio-scraper instead of Playwright to save massive amounts of credits
    run_input = {
        "startUrls": [{"url": url}],
        "useApifyProxy": True,
    }
    
    try:
        run = client.actor("apify/cheerio-scraper").call(
            run_input=run_input,
            timeout_secs=60,
            wait_secs=70,
        )
        if not run:
            return None
        
        for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            if item.get("url") == url or url in item.get("url", ""):
                text = item.get("text", "") or item.get("body", "")
                word_count = len(text.split()) if text else 0
                title = item.get("pageTitle", "") or item.get("title", "")
                
                # Cheerio scraper might not extract raw text by default,
                # but if we extract it, we use it. 
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
