import os
import logging
from typing import List, Dict, Any

from app.config import settings
from nlp.website_prompts import analyze_website_intent, generate_website_prompt, audit_website_prompt
from scraping.apify_client_module import search_google_via_apify, extract_apify_page_content

logger = logging.getLogger(__name__)

# Path to the master prompt theme file
THEME_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "master-prompt-theme.txt")


def get_master_theme_text() -> str:
    try:
        with open(THEME_FILE_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Could not read {THEME_FILE_PATH}: {e}")
        return ""


def analyze_intent_flow(keyword: str, manual_competitors: List[str] = None, short_mode: bool = False) -> Dict[str, Any]:
    """
    Analyzes intent and generates competitor URLs entirely via AI.
    No Apify scraping is performed.
    """
    ai_result = analyze_website_intent(keyword, short_mode=short_mode)
    intent = ai_result.get("intent", "Informational Website")
    
    # If the user provided manual competitors, prioritize those over AI-generated ones
    competitors = manual_competitors or []
    if not competitors:
        competitors = ai_result.get("competitors", [])

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


def generate_gap_page_flow(keyword: str, intent: str, competitors: List[str]) -> Dict[str, Any]:
    """
    Generates a single Gap Page Prompt.
    Just returns a specific prompt for a single page for the given keyword and intent.
    It does not append the master theme.
    """
    prompt = (
        "========================================================================\n"
        "SINGLE GAP PAGE SPECIFICATION\n"
        "========================================================================\n\n"
        f"TARGET KEYWORD: {keyword}\n"
        f"PAGE INTENT: {intent}\n\n"
        "Please generate a complete structure as per the website theme and constraints and content for a single standalone page that specifically caters to the target keyword and intent above.\n"
        "The page should be highly optimized for SEO based on this keyword, provide the exact utility or information required by the intent, and follow modern web design principles.\n"
        "Generate the page and follow the already existing design prefrences and structure do not genrate sperately from scrach\n"
    )

    return {
        "prompt": prompt,
        "audit_score": 100,
        "attempts": 1
    }
