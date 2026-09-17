import logging
import math
import time
from typing import List, Dict, Any, Optional
from apify_client import ApifyClient
from app.config import settings
from scraping.crawler import ScrapedPage

logger = logging.getLogger(__name__)
_ACCOUNT_STATUS_CACHE: tuple[float, Dict[str, Any]] | None = None

def is_apify_configured() -> bool:
    return bool(settings.APIFY_API_TOKEN)

def _get_client() -> ApifyClient:
    return ApifyClient(settings.APIFY_API_TOKEN)


def apify_account_status(force: bool = False) -> Dict[str, Any]:
    """Validate the configured token without starting a paid actor run."""
    global _ACCOUNT_STATUS_CACHE
    now = time.monotonic()
    if not force and _ACCOUNT_STATUS_CACHE and now - _ACCOUNT_STATUS_CACHE[0] < 300:
        return dict(_ACCOUNT_STATUS_CACHE[1])
    if not is_apify_configured():
        result = {
            "configured": False,
            "authenticated": False,
            "credential_source": None,
            "message": "Add APIFY_API_TOKEN in Render.",
        }
    else:
        try:
            user = _get_client().user().get()
            authenticated = isinstance(user, dict) and bool(user.get("id"))
            result = {
                "configured": True,
                "authenticated": authenticated,
                "credential_source": "APIFY_API_TOKEN",
                "message": "Connected to Apify." if authenticated else "Apify rejected the configured token.",
            }
        except Exception as exc:
            result = {
                "configured": True,
                "authenticated": False,
                "credential_source": "APIFY_API_TOKEN",
                "message": f"Could not verify Apify: {type(exc).__name__}",
            }
    _ACCOUNT_STATUS_CACHE = (now, result)
    return dict(result)

def search_google_via_apify(query: str, max_results: int = 30, country_code: str = "us") -> List[Dict[str, Any]]:
    """
    Search Google using the configured competitor discovery Actor.
    Scrapes enough pages to satisfy max_results (the Actor returns ten per page).
    Returns structured organic results with url, title, snippet.
    """
    if not is_apify_configured():
        logger.warning("Apify not configured. Skipping Google search via Apify.")
        return []

    client = _get_client()
    all_results: List[Dict[str, Any]] = []
    seen_urls: set[str] = set()
    pages_to_scrape = max(1, math.ceil(max_results / 10))

    for page_num in range(1, pages_to_scrape + 1):
        run_input = {
            "keyword": query,
            "limit": "10",
            "page": page_num,
            "country": country_code.upper(),
        }

        try:
            logger.info(
                "Running Apify competitor scraper for query: %r page %s",
                query, page_num,
            )
            run = client.actor(settings.APIFY_COMPETITOR_ACTOR_ID).call(
                run_input=run_input,
                timeout_secs=90,
                wait_secs=100,
            )
            if not run:
                logger.error(
                    "Apify SERP scraper returned no run metadata for %r page %s",
                    query, page_num,
                )
                continue
            if run.get("status") != "SUCCEEDED":
                logger.error(
                    "Apify SERP scraper did not succeed for %r page %s: status=%s message=%s",
                    query,
                    page_num,
                    run.get("status"),
                    run.get("statusMessage") or run.get("status_message") or "none",
                )
                continue

            for item in client.dataset(run["defaultDatasetId"]).iterate_items():
                # The actor returns {results: [...], next_page, next_start}
                serp_results = item.get("results") or item.get("searchResults") or []
                # Handle case where results might be a JSON string
                if isinstance(serp_results, str):
                    try:
                        import json
                        serp_results = json.loads(serp_results)
                    except (json.JSONDecodeError, TypeError):
                        serp_results = []

                if isinstance(serp_results, list):
                    for res in serp_results:
                        if not isinstance(res, dict):
                            continue
                        url = res.get("url") or res.get("link")
                        if not url or url in seen_urls:
                            continue
                        if url.startswith("https://apify.com/"):
                            continue
                        seen_urls.add(url)
                        all_results.append({
                            "url": url,
                            "title": res.get("title"),
                            "snippet": res.get("description") or res.get("snippet"),
                        })
                # Also handle flat item format (some actors return one item per result)
                elif not serp_results:
                    url = item.get("url") or item.get("link")
                    if url and url not in seen_urls and not url.startswith("https://apify.com/"):
                        seen_urls.add(url)
                        all_results.append({
                            "url": url,
                            "title": item.get("title"),
                            "snippet": item.get("description") or item.get("snippet"),
                        })

        except Exception as exc:
            logger.error("Apify SERP scraper failed for %r page %s: %s", query, page_num, exc)
            continue

        if len(all_results) >= max_results:
            break

    if not all_results:
        logger.warning("Apify SERP scraper returned no organic results for %r across %s pages", query, pages_to_scrape)
    else:
        logger.info(
            "Apify SERP scraper returned %s organic results for %r across %s pages",
            len(all_results), query, pages_to_scrape,
        )
    return all_results[:max_results]


def research_keywords_via_apify(
    seed_keywords: List[str],
    country_code: str = "us",
    language: str | None = None,
    max_results_per_seed: int | None = None,
) -> List[Dict[str, Any]]:
    """Run the keyword research Actor once for every seed and merge its results."""
    if not is_apify_configured():
        logger.warning("Apify not configured. Skipping keyword research.")
        return []

    client = _get_client()
    actor_id = settings.APIFY_KEYWORD_ACTOR_ID
    result_limit = max(1, min(500, max_results_per_seed or settings.APIFY_KEYWORD_RESULT_LIMIT))
    locale = (country_code or "us").strip().lower()[:2]
    result_language = (language or settings.APIFY_KEYWORD_LANGUAGE or "en").strip().lower()[:2]
    merged: Dict[str, Dict[str, Any]] = {}

    for raw_seed in seed_keywords:
        seed = str(raw_seed or "").strip()
        if not seed:
            continue
        run_input = {
            "keyword": seed,
            "country": locale,
            "language": result_language,
            "limit": result_limit,
            "min_volume": max(0, settings.APIFY_KEYWORD_MIN_VOLUME),
        }
        try:
            logger.info("Running Apify keyword research for exact seed %r", seed)
            run = client.actor(actor_id).call(
                run_input=run_input,
                timeout_secs=300,
                wait_secs=310,
            )
            if not run or run.get("status") != "SUCCEEDED":
                logger.error(
                    "Apify keyword research did not succeed for %r: status=%s message=%s",
                    seed,
                    (run or {}).get("status"),
                    (run or {}).get("statusMessage") or (run or {}).get("status_message") or "none",
                )
                continue

            for item in client.dataset(run["defaultDatasetId"]).iterate_items():
                if not isinstance(item, dict):
                    continue
                phrase = str(item.get("keyword") or item.get("phrase") or "").strip().lower()
                if not phrase:
                    continue
                normalized = {
                    "phrase": phrase,
                    "search_volume": _number_or_none(item.get("volume") or item.get("search_volume"), int),
                    "difficulty": _number_or_none(item.get("sd") or item.get("difficulty"), float),
                    "cpc": _number_or_none(item.get("cpc_usd") or item.get("cpc"), float),
                    "intent": str(item.get("intent") or "").strip().lower() or None,
                    "seed_keywords": [seed],
                }
                existing = merged.get(phrase)
                if existing:
                    if seed not in existing["seed_keywords"]:
                        existing["seed_keywords"].append(seed)
                    if (normalized["search_volume"] or 0) > (existing.get("search_volume") or 0):
                        existing.update({
                            key: value for key, value in normalized.items()
                            if key != "seed_keywords" and value is not None
                        })
                else:
                    merged[phrase] = normalized
        except Exception as exc:
            logger.error("Apify keyword research failed for exact seed %r: %s", seed, exc)

    logger.info(
        "Apify keyword research returned %s unique keywords across %s seeds",
        len(merged),
        len([seed for seed in seed_keywords if str(seed or "").strip()]),
    )
    return list(merged.values())


def _number_or_none(value: Any, number_type: type) -> int | float | None:
    if value is None or value == "":
        return None
    try:
        return number_type(value)
    except (TypeError, ValueError):
        return None

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
            logger.error("Apify content crawl returned no run metadata for %s", domain_or_url)
            return []
        if run.get("status") != "SUCCEEDED":
            logger.error(
                "Apify content crawl did not succeed for %s: status=%s message=%s",
                domain_or_url,
                run.get("status"),
                run.get("statusMessage") or run.get("status_message") or "none",
            )
            return []
        
        urls = []
        for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            url = item.get("url")
            if url:
                urls.append(url)
        logger.info("Apify content crawl returned %s URLs for %s", len(urls), domain_or_url)
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
