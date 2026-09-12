"""
DeepSeek-powered SEO keyword enrichment.

Sends batches of keywords to the DeepSeek API to get estimated search volume,
keyword difficulty, and AI-powered SEO recommendations.
"""

import json
import logging
from typing import Any

from openai import OpenAI

from app.config import settings

logger = logging.getLogger(__name__)

# Maximum keywords per DeepSeek API call to stay within token limits
_BATCH_SIZE = 25


def _get_deepseek_client() -> OpenAI | None:
    """Return a DeepSeek-configured OpenAI client, or None if not configured."""
    api_key = settings.DEEPSEEK_API_KEY.strip()
    if not api_key:
        return None
    return OpenAI(
        base_url="https://api.deepseek.com",
        api_key=api_key,
        timeout=settings.AI_REQUEST_TIMEOUT,
        max_retries=1,
    )


def is_deepseek_configured() -> bool:
    return bool(settings.DEEPSEEK_API_KEY.strip())


def _strip_code_fences(content: str) -> str:
    value = (content or "").strip()
    if value.startswith("```json"):
        return value[7:-3].strip()
    if value.startswith("```"):
        return value[3:-3].strip()
    return value


def _enrich_batch(
    client: OpenAI,
    keyword_phrases: list[str],
    seed_keywords: list[str],
    niche_context: str | None = None,
) -> list[dict[str, Any]]:
    """Call DeepSeek to estimate SEO metrics for a batch of keywords."""
    seeds_str = ", ".join(seed_keywords[:5])
    context_block = ""
    if niche_context:
        context_block = f"\nNiche context: {niche_context[:1000]}\n"

    keywords_json = json.dumps(keyword_phrases, indent=2)

    prompt = f"""You are an SEO expert analyst. For each keyword below, estimate:
1. **search_volume**: Estimated monthly Google search volume (integer). Use your knowledge of search trends. Be realistic — most long-tail keywords get 50-500 searches/month.
2. **difficulty**: Keyword difficulty score from 0-100 (float). 0 = easiest to rank for, 100 = hardest. Consider domain authority of competing sites, content quality needed, and commercial intent.
3. **recommendation**: A concise, actionable SEO recommendation (1-2 sentences) for how a website in this niche should target this keyword. Include content type suggestions (blog post, landing page, comparison article, etc.).

The seed keywords for this website's niche are: {seeds_str}
{context_block}
Keywords to analyze:
{keywords_json}

Return ONLY a JSON array where each element has:
{{"keyword": "...", "search_volume": 123, "difficulty": 45.0, "recommendation": "..."}}

Important rules:
- Return the EXACT same keyword strings as provided
- search_volume must be a positive integer
- difficulty must be a float between 0 and 100
- recommendation must be a brief, specific, actionable string
- Do NOT add any explanation outside the JSON array"""

    try:
        model = settings.DEEPSEEK_MODEL or "deepseek-chat"
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=4000,
        )
        content = response.choices[0].message.content or ""
        cleaned = _strip_code_fences(content)
        parsed = json.loads(cleaned)

        if isinstance(parsed, list):
            return [
                item for item in parsed
                if isinstance(item, dict)
                and "keyword" in item
                and isinstance(item.get("search_volume"), (int, float))
            ]
        return []

    except json.JSONDecodeError as exc:
        logger.warning("DeepSeek SEO response was not valid JSON: %s", exc)
        return []
    except Exception as exc:
        logger.error("DeepSeek SEO enrichment API call failed: %s", exc)
        return []


def enrich_keywords_with_seo_data(
    keyword_phrases: list[str],
    seed_keywords: list[str],
    audit_summary: str | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Enrich keywords with SEO data from DeepSeek.

    Returns a dict mapping keyword phrase -> {search_volume, difficulty, recommendation}.
    Keywords not successfully enriched are omitted from the result.
    """
    client = _get_deepseek_client()
    if not client:
        logger.warning("DeepSeek not configured. Skipping SEO keyword enrichment.")
        return {}

    if not keyword_phrases:
        return {}

    # Deduplicate while preserving order
    unique_phrases = list(dict.fromkeys(keyword_phrases))
    result: dict[str, dict[str, Any]] = {}

    # Process in batches
    for i in range(0, len(unique_phrases), _BATCH_SIZE):
        batch = unique_phrases[i:i + _BATCH_SIZE]
        logger.info(
            "Enriching SEO data for keywords batch %s-%s of %s",
            i + 1, min(i + _BATCH_SIZE, len(unique_phrases)), len(unique_phrases),
        )

        enriched = _enrich_batch(
            client,
            batch,
            seed_keywords,
            niche_context=audit_summary,
        )

        for item in enriched:
            kw = str(item.get("keyword", "")).strip().lower()
            if not kw:
                continue
            result[kw] = {
                "search_volume": int(item.get("search_volume") or 0),
                "difficulty": round(float(item.get("difficulty") or 0), 1),
                "recommendation": str(item.get("recommendation") or "")[:500],
            }

    logger.info("DeepSeek SEO enrichment complete: %s of %s keywords enriched", len(result), len(unique_phrases))
    return result
