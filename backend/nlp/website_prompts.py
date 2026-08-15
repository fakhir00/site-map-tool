import json
from typing import Any, Dict, List

from nlp.openrouter import _chat_json, _chat_text

def analyze_website_intent(keyword: str, short_mode: bool = False) -> Dict[str, Any]:
    """
    Analyzes the keyword to determine the user intent and generates a list of example competitor domains.
    Returns a dictionary with 'intent' (str) and 'competitors' (list of str).
    """
    intent_instruction = (
        "The intent must be exactly ONE hyphenated word summarizing the intent (e.g. 'tool-page', 'blog-page', 'info-page', 'ecommerce-page'). Do not output a paragraph.\n"
        if short_mode
        else "Be concise but descriptive. Provide a single paragraph describing the intent and the type of website needed.\n"
    )

    system_prompt = (
        "You are an expert SEO and product strategist. Your job is to analyze a target keyword.\n"
        "1. Determine the core 'Website Intent' for this keyword. Is it a calculator? A survey? A SaaS tool? An informational blog? An e-commerce store? A local service page?\n"
        f"{intent_instruction}"
        "2. Provide a list of 3-5 real-world example competitor domains or tools that match this keyword and intent.\n\n"
        "OUTPUT FORMAT: You MUST return a valid JSON object with EXACTLY two keys:\n"
        "- \"intent\": string\n"
        "- \"competitors\": array of strings (URLs or domain names)"
    )
    
    user_prompt = f"Keyword: {keyword}\n\nWhat is the intent of this keyword and what are some top competitors?"

    try:
        response_json = _chat_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.6,
            max_tokens=400,
        )
        return response_json
    except Exception as e:
        logger.error(f"Failed to analyze intent and competitors: {e}")
        return {"intent": "Informational/Standard Website", "competitors": []}


def generate_website_prompt(keyword: str, intent: str, master_theme_text: str, revision_notes: List[str] = None) -> str:
    """
    Generates the Website Master Prompt based on the keyword, verified intent, and the 
    master-prompt-theme.txt rules.
    """
    system_prompt = (
        "You are an elite AI Architect and SEO Prompt Engineer. Your task is to generate strict supplementary instructions to be appended to a 'Template Master Prompt'.\n\n"
        "CRITICAL INSTRUCTIONS:\n"
        "1. DO NOT REWRITE OR OUTPUT THE ORIGINAL TEMPLATE. The backend will automatically prepend it.\n"
        "2. ONLY OUTPUT THE SUPPLEMENTARY SECTIONS.\n"
        "3. ADD 'SPECIAL SPECIFICATION' SECTION: You MUST output a section titled '========================================================================\\nSPECIAL SPECIFICATION\\n========================================================================'. In this section, define the situation-specific features for the Keyword and Intent (e.g., exact interactive features, calculators, SaaS forms, etc.).\n"
        "4. ADD 'SILO STRUCTURE' SECTION: You MUST output a section titled '========================================================================\\nSILO STRUCTURE\\n========================================================================'. In this section, define the URL silo architecture and content mapping for the keyword.\n"
        "5. The output must be raw text (ready to be copy-pasted). Do NOT output markdown wrappers (like ```markdown) at the top/bottom."
    )
    
    if revision_notes:
        system_prompt += "\n\nPREVIOUS AUDIT FAILED. Please fix the following issues:\n- " + "\n- ".join(revision_notes)

    user_prompt = (
        f"KEYWORD: {keyword}\n"
        f"INTENT: {intent}\n\n"
        "Generate the supplementary Special Specification and Silo Structure sections now."
    )

    try:
        response_text = _chat_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.7,
            max_tokens=4000,
        )
        # Programmatically combine the raw master template with the LLM's generated sections
        header = (
            "========================================================================\n"
            "PRIMARY KEYWORD & INTENT SPECIFICATION\n"
            "========================================================================\n\n"
            f"TARGET KEYWORD: {keyword}\n"
            f"WEBSITE INTENT: {intent}\n\n"
            "Please build a website that specifically caters to the target keyword and intent above.\n"
            "Make sure to include necessary pages, tools, calculators, or layouts that satisfy this intent.\n\n"
        )
        combined_prompt = f"{header}{response_text.strip()}\n\n{master_theme_text}"
        return combined_prompt
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
