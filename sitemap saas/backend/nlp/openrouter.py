import json
import logging
from typing import List, Dict, Any
from openai import AsyncOpenAI, OpenAI
from app.config import settings

logger = logging.getLogger(__name__)

async def generate_ai_keywords(seed_keywords: List[str]) -> List[Dict[str, Any]]:
    """Generate SEO keyword recommendations using OpenRouter API."""
    if not settings.OPENROUTER_API_KEY:
        logger.error("OpenRouter API key not configured")
        return []
        
    client = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.OPENROUTER_API_KEY,
    )
    
    prompt = f"""
You are an expert SEO analyst. Based on the following seed keywords, generate a list of exactly 15 highly relevant, low-competition keyword opportunities.
Provide a mix of primary, LSI, and long-tail keywords.

Seed Keywords: {", ".join(seed_keywords)}

Return ONLY a JSON array of objects. Do not include any markdown formatting, explanation, or code blocks. Just the raw JSON.
Each object must have:
- "phrase": the keyword phrase (string, lowercase)
- "type": one of "primary", "lsi", or "long-tail"

Example output:
[
  {{"phrase": "best seo tools", "type": "primary"}},
  {{"phrase": "seo tools for small business", "type": "long-tail"}},
  {{"phrase": "search engine optimization", "type": "lsi"}}
]
"""
    try:
        response = await client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You output only valid JSON arrays."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
        )
        content = response.choices[0].message.content.strip()
        
        # Clean up possible markdown wrappers
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
            
        keywords = json.loads(content)
        
        # Handle cases where LLM wraps it in a dict
        if isinstance(keywords, dict) and "keywords" in keywords:
            keywords = keywords["keywords"]
            
        valid_keywords = []
        for kw in keywords:
            if isinstance(kw, dict) and kw.get("phrase"):
                kw_type = kw.get("type", "lsi").lower().strip()
                if kw_type not in ["primary", "lsi", "long-tail"]:
                    kw_type = "lsi"
                valid_keywords.append({
                    "phrase": kw["phrase"].lower().strip(),
                    "type": kw_type
                })
                
        return valid_keywords
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON from OpenRouter: {e}\nContent was: {content}")
        return []
    except Exception as e:
        logger.error(f"Failed to generate keywords via OpenRouter: {e}")
        return []


def filter_keyword_gap_recommendations(
    seed_keywords: List[str],
    candidates: List[Dict[str, Any]],
    max_keywords: int = 60,
) -> List[Dict[str, Any]]:
    """Use AI to keep and improve the strongest competitor sitemap gap keywords."""
    if not settings.OPENROUTER_API_KEY:
        logger.info("OpenRouter API key not configured; skipping AI keyword gap filter")
        return []
    if not candidates:
        return []

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.OPENROUTER_API_KEY,
    )

    trimmed_candidates = candidates[: settings.AI_KEYWORD_GAP_CANDIDATE_LIMIT]
    prompt = f"""
You are an expert SEO strategist filtering keyword gap recommendations.

The user's target seed keywords are:
{json.dumps(seed_keywords)}

Below are candidate keyword gaps extracted from top-ranking competitor sitemaps.
Each candidate includes the original phrase, competitor page count, competitor domain count, and current type.

Candidates:
{json.dumps(trimmed_candidates, ensure_ascii=True)}

Return ONLY a JSON array. Select up to {max_keywords} candidates that are genuinely useful content or landing-page opportunities for this site.
Remove thin, generic, navigational, off-topic, duplicate, brand-only, and awkward sitemap-slug phrases.
You may lightly improve wording, but keep the intent grounded in the source phrase.

Each returned object must include:
- "source_phrase": exact original phrase from the candidates
- "phrase": improved lowercase keyword phrase
- "type": one of "primary", "lsi", or "long-tail"

Do not include markdown, commentary, scores, or keys beyond those three fields.
"""

    try:
        response = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You output only valid JSON arrays."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        content = (response.choices[0].message.content or "").strip()
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()

        payload = json.loads(content)
        if isinstance(payload, dict) and "keywords" in payload:
            payload = payload["keywords"]
        if not isinstance(payload, list):
            return []

        valid: List[Dict[str, Any]] = []
        candidate_phrases = {
            str(candidate.get("phrase", "")).strip().lower()
            for candidate in trimmed_candidates
            if candidate.get("phrase")
        }
        for item in payload:
            if not isinstance(item, dict):
                continue
            source_phrase = str(item.get("source_phrase") or item.get("source") or "").strip().lower()
            phrase = str(item.get("phrase") or "").strip().lower()
            keyword_type = str(item.get("type") or "lsi").strip().lower()
            if keyword_type not in {"primary", "lsi", "long-tail"}:
                keyword_type = "lsi"
            if not source_phrase and phrase in candidate_phrases:
                source_phrase = phrase
            if not source_phrase or source_phrase not in candidate_phrases or not phrase:
                continue
            valid.append({
                "source_phrase": source_phrase,
                "phrase": phrase,
                "type": keyword_type,
            })
            if len(valid) >= max_keywords:
                break

        return valid
    except json.JSONDecodeError as e:
        logger.error("Failed to parse JSON from OpenRouter gap filter: %s", e)
        return []
    except Exception as e:
        logger.error("Failed to filter keyword gaps via OpenRouter: %s", e)
        return []
