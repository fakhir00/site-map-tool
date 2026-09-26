"""
DeepSeek-powered SEO keyword enrichment.

Uses DeepSeek for editorial recommendations only. Search volume and difficulty
must come from measured research providers, never language-model estimates.
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
    """Ask DeepSeek for editorial guidance without estimating SEO metrics."""
    seeds_str = ", ".join(seed_keywords[:5])
    context_block = ""
    if niche_context:
        context_block = f"\nNiche context: {niche_context[:1000]}\n"

    keywords_json = json.dumps(keyword_phrases, indent=2)

    prompt = f"""Suggest a concise editorial recommendation for each supplied keyword.
Website seeds: {seeds_str}
{context_block}
Keywords: {keywords_json}
Return only a JSON array of objects with the exact supplied "keyword" and a
"recommendation" (one or two sentences describing a useful content approach).
Do not estimate search volume, difficulty, ranking probability or competitor authority.
Do not invent facts or imply that a topic is a verified gap.
"""

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
                and isinstance(item.get("recommendation"), str)
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
    Enrich keywords with editorial guidance from DeepSeek.

    Returns a dict mapping keyword phrase -> {search_volume, difficulty, recommendation}.
    Metric fields remain None; keywords not successfully enriched are omitted.
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
            if kw not in {phrase.lower() for phrase in batch}:
                continue
            result[kw] = {
                "search_volume": None,
                "difficulty": None,
                "recommendation": str(item.get("recommendation") or "")[:500],
            }

    logger.info("DeepSeek SEO enrichment complete: %s of %s keywords enriched", len(result), len(unique_phrases))
    return result
