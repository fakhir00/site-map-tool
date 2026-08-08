import os
import logging
from typing import List, Dict, Any

from app.config import settings
from nlp.website_prompts import analyze_website_intent, generate_website_prompt, audit_website_prompt
from scraping.apify_client_module import search_google_via_apify, extract_apify_page_content

logger = logging.getLogger(__name__)

# Path to the master prompt theme file
THEME_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "master-prompt-theme.txt")


def get_master_theme_text() -> str:
    try:
        with open(THEME_FILE_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Could not read {THEME_FILE_PATH}: {e}")
        return ""


def analyze_intent_flow(keyword: str, manual_competitors: List[str] = None) -> Dict[str, Any]:
    """
    Scrapes competitor homepages and analyzes intent.
    If manual_competitors is empty, it uses Apify SERP scraper to get the top 5.
    """
    competitors = manual_competitors or []
    
    if not competitors:
        try:
            apify_results = search_google_via_apify(keyword, max_results=5)
            competitors = [res["url"] for res in apify_results if "url" in res]
        except Exception as e:
            logger.error(f"Failed to fetch SERP competitors for '{keyword}': {e}")

    # Scrape the content of these homepages
    scraped_texts = []
    for url in competitors[:5]:
        try:
            page = extract_apify_page_content(url)
            if page and page.markdown_content:
                scraped_texts.append(page.markdown_content)
        except Exception as e:
            logger.error(f"Failed to extract content for {url}: {e}")

    # Analyze intent
    if not scraped_texts:
        intent = "Informational Website (Could not scrape competitor contents)"
    else:
        intent = analyze_website_intent(keyword, scraped_texts)

    return {
        "intent": intent,
        "competitors": competitors[:5]
    }


def generate_prompt_flow(keyword: str, intent: str, competitors: List[str]) -> Dict[str, Any]:
    """
    Generates the Website Master Prompt and audits it.
    Retries up to 3 times if the auditor fails.
    """
    master_theme_text = get_master_theme_text()
    
    max_attempts = 3
    revision_notes = []
    best_prompt = ""
    best_audit = {"passed": False, "score": 0}
    
    for attempt in range(1, max_attempts + 1):
        prompt = generate_website_prompt(keyword, intent, master_theme_text, revision_notes)
        
        audit = audit_website_prompt(prompt)
        
        if audit.get("passed"):
            return {
                "prompt": prompt,
                "audit_score": audit.get("score", 100),
                "attempts": attempt
            }
            
        # Update best prompt just in case we run out of attempts
        if audit.get("score", 0) >= best_audit.get("score", 0):
            best_prompt = prompt
            best_audit = audit
            
        revision_notes = audit.get("issues", [])

    return {
        "prompt": best_prompt,
        "audit_score": best_audit.get("score", 0),
        "attempts": max_attempts
    }
