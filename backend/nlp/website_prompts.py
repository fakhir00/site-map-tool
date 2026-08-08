import json
import logging
from typing import Any, Dict, List

from nlp.openrouter import _chat_text

logger = logging.getLogger(__name__)

def analyze_website_intent(keyword: str, scraped_texts: List[str]) -> str:
    """
    Analyzes the scraped homepage contents of top competitors to determine the
    user intent and website archetype for the given keyword.
    """
    combined_content = "\n\n---\n\n".join([text[:3000] for text in scraped_texts])  # limit tokens
    
    system_prompt = (
        "You are an expert SEO and product strategist. Your job is to analyze the text content "
        "from the homepages of the top-ranking competitors for a specific keyword.\n"
        "Determine the core 'Website Intent'. Is it a calculator? A survey? A SaaS tool? An informational blog? An e-commerce store?\n"
        "Be concise but descriptive. Output a single paragraph describing the intent and the type of website needed."
    )
    
    user_prompt = f"Keyword: {keyword}\n\nCompetitor Homepage Contents:\n{combined_content}\n\nWhat is the intent of this keyword and what type of website should we build?"

    try:
        response_text = _chat_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.4,
            max_tokens=300,
        )
        return response_text.strip()
    except Exception as e:
        logger.error(f"Failed to analyze intent: {e}")
        return "Informational/Standard Website"


def generate_website_prompt(keyword: str, intent: str, master_theme_text: str, revision_notes: List[str] = None) -> str:
    """
    Generates the Website Master Prompt based on the keyword, verified intent, and the 
    master-prompt-theme.txt rules.
    """
    system_prompt = (
        "You are an elite AI Architect and SEO Prompt Engineer. Your task is to take a generic 'Template Master Prompt' and tailor it for a specific KEYWORD and INTENT.\n\n"
        "CRITICAL INSTRUCTIONS:\n"
        "1. PRESERVE THE TEMPLATE: You MUST output the ENTIRE Template Master Prompt exactly as it is written, preserving all of its original rules, formatting, and sections. DO NOT summarize or omit anything from the original template.\n"
        "2. MINOR TWEAKS: You may make minor edits to the original text ONLY to replace generic terms with the specific keyword or intent (e.g., specifying it's a calculator instead of a generic site), but do not delete any core rules.\n"
        "3. ADD 'SPECIAL SPECIFICATION' SECTION: You MUST ADD a brand new section titled '========================================================================\\nSPECIAL SPECIFICATION\\n========================================================================'. In this section, define the situation-specific features for the Keyword and Intent (e.g., exact interactive features, calculators, SaaS forms, etc.).\n"
        "4. ADD 'SILO STRUCTURE' SECTION: You MUST ADD a brand new section titled '========================================================================\\nSILO STRUCTURE\\n========================================================================'. In this section, define the URL silo architecture and content mapping for the keyword.\n"
        "5. The output must be the raw tailored prompt text (ready to be copy-pasted). Do NOT output markdown wrappers (like ```markdown) at the top/bottom."
    )
    
    if revision_notes:
        system_prompt += "\n\nPREVIOUS AUDIT FAILED. Please fix the following issues:\n- " + "\n- ".join(revision_notes)

    user_prompt = (
        f"KEYWORD: {keyword}\n"
        f"INTENT: {intent}\n\n"
        f"--- TEMPLATE MASTER PROMPT ---\n{master_theme_text}\n--- END TEMPLATE ---\n\n"
        "Generate the full, highly specific, customized Website Master Prompt now."
    )

    try:
        response_text = _chat_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.7,
            max_tokens=4000,
        )
        return response_text.strip()
    except Exception as e:
        logger.error(f"Failed to generate website prompt: {e}")
        return ""


def audit_website_prompt(prompt: str) -> Dict[str, Any]:
    """
    Audits the generated Website Master Prompt to ensure it didn't drop critical constraints.
    """
    system_prompt = (
        "You are a strict QA Auditor for AI Prompts. You must verify that the provided 'Website Master Prompt' "
        "contains specific required directives.\n"
        "You must return ONLY a valid JSON object matching this schema:\n"
        "{\n"
        "  \"passed\": boolean,\n"
        "  \"score\": integer (0-100),\n"
        "  \"issues\": [\"list of missing requirements\"],\n"
        "  \"strengths\": [\"list of good points\"]\n"
        "}\n\n"
        "Checklist of REQUIRED items:\n"
        "1. Must explicitly mandate an Astro/Tailwind stack.\n"
        "2. Must explicitly define a 'Silo Structure' with URL mapping examples specific to the keyword.\n"
        "3. Must explicitly describe the specific Intent (e.g., if it's a calculator or tool, it must outline those features).\n"
        "4. Must explicitly mandate I18N/Language localization pages.\n"
        "5. Must explicitly mandate essential pages (About Us, Contact Us, Terms, Privacy, Sitemap).\n"
        "If ANY of these 5 are missing, passed MUST be false and the score should be penalized."
    )
    
    user_prompt = f"Audit this prompt:\n\n{prompt}"
    
    try:
        response_text = _chat_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.1,
            max_tokens=1000,
        )
        
        # Clean markdown formatting if present
        text = response_text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
            
        data = json.loads(text.strip())
        return data
    except Exception as e:
        logger.error(f"Failed to audit website prompt: {e}")
        return {
            "passed": False,
            "score": 0,
            "issues": ["Failed to parse auditor response JSON."],
            "strengths": []
        }
