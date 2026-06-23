import json
import logging
from typing import Any

from openai import AsyncOpenAI, OpenAI

from app.config import settings

logger = logging.getLogger(__name__)


def _is_configured() -> bool:
    return bool(settings.OPENROUTER_API_KEY)


def _sync_client() -> OpenAI:
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.OPENROUTER_API_KEY,
    )


def _async_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.OPENROUTER_API_KEY,
    )


def _strip_code_fences(content: str) -> str:
    value = (content or "").strip()
    if value.startswith("```json"):
        return value[7:-3].strip()
    if value.startswith("```"):
        return value[3:-3].strip()
    return value


def _parse_json_payload(content: str) -> Any:
    payload = json.loads(_strip_code_fences(content))
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


async def _achat_json(
    *,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
) -> Any:
    client = _async_client()
    response = await client.chat.completions.create(
        model=settings.OPENROUTER_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
    )
    return _parse_json_payload(response.choices[0].message.content or "")


def _chat_json(
    *,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
) -> Any:
    client = _sync_client()
    response = client.chat.completions.create(
        model=settings.OPENROUTER_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
    )
    return _parse_json_payload(response.choices[0].message.content or "")


def _chat_text(
    *,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.3,
) -> str:
    client = _sync_client()
    response = client.chat.completions.create(
        model=settings.OPENROUTER_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
    )
    return (response.choices[0].message.content or "").strip()


async def generate_ai_keywords(seed_keywords: list[str]) -> list[dict[str, Any]]:
    """Generate SEO keyword recommendations using OpenRouter API."""
    if not _is_configured():
        logger.error("OpenRouter API key not configured")
        return []

    prompt = f"""
You are an expert SEO analyst. Based on the following seed keywords, generate a list of exactly 15 highly relevant, low-competition keyword opportunities.
Provide a mix of primary, LSI, and long-tail keywords.

Seed Keywords: {", ".join(seed_keywords)}

Return ONLY a JSON array of objects. Do not include markdown formatting, explanation, or code blocks.
Each object must have:
- "phrase": the keyword phrase (string, lowercase)
- "type": one of "primary", "lsi", or "long-tail"
"""
    try:
        payload = await _achat_json(
            system_prompt="You output only valid JSON arrays.",
            user_prompt=prompt,
            temperature=0.7,
        )
        if isinstance(payload, dict) and "keywords" in payload:
            payload = payload["keywords"]
        if not isinstance(payload, list):
            return []

        valid_keywords = []
        for kw in payload:
            if isinstance(kw, dict) and kw.get("phrase"):
                kw_type = str(kw.get("type", "lsi")).lower().strip()
                if kw_type not in ["primary", "lsi", "long-tail"]:
                    kw_type = "lsi"
                valid_keywords.append({
                    "phrase": str(kw["phrase"]).lower().strip(),
                    "type": kw_type,
                })
        return valid_keywords
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse JSON from OpenRouter: %s", exc)
        return []
    except Exception as exc:
        logger.error("Failed to generate keywords via OpenRouter: %s", exc)
        return []


def filter_keyword_gap_recommendations(
    seed_keywords: list[str],
    candidates: list[dict[str, Any]],
    max_keywords: int = 60,
) -> list[dict[str, Any]]:
    """Use AI to keep and improve the strongest competitor sitemap gap keywords."""
    if not _is_configured():
        logger.info("OpenRouter API key not configured; skipping AI keyword gap filter")
        return []
    if not candidates:
        return []

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
"""

    try:
        payload = _chat_json(
            system_prompt="You output only valid JSON arrays.",
            user_prompt=prompt,
            temperature=0.2,
        )
        if isinstance(payload, dict) and "keywords" in payload:
            payload = payload["keywords"]
        if not isinstance(payload, list):
            return []

        valid: list[dict[str, Any]] = []
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
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse JSON from OpenRouter gap filter: %s", exc)
        return []
    except Exception as exc:
        logger.error("Failed to filter keyword gaps via OpenRouter: %s", exc)
        return []


def judge_competitor_domains(
    seed_keywords: list[str],
    own_domain: str,
    candidates: list[dict[str, Any]],
    max_domains: int,
) -> list[dict[str, Any]]:
    """Use the LLM as the final gatekeeper for whether a domain is a true competitor."""
    if not _is_configured() or not candidates:
        return []

    prompt = f"""
You are the final competitor judge for an SEO SaaS.

Target site:
{own_domain}

Primary keyword set:
{json.dumps(seed_keywords)}

Candidate competitors:
{json.dumps(candidates, ensure_ascii=True)}

Choose only domains that are real search competitors for the target keywords. Accept sites that directly compete for the same search intent, audience, and topic cluster. Reject dictionaries, marketplaces, social networks, forums, docs portals, tool directories, unrelated apps, and generic informational sites unless they clearly rank as direct alternatives for the same use case.

Return ONLY a JSON array with up to {max_domains} objects.
Each object must include:
- "domain": accepted candidate domain
- "verdict": "accept" or "reject"
- "confidence": integer from 0 to 100
- "reason": short string
"""

    try:
        payload = _chat_json(
            system_prompt="You output only valid JSON arrays.",
            user_prompt=prompt,
            temperature=0.1,
        )
        if not isinstance(payload, list):
            return []

        accepted: list[dict[str, Any]] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            verdict = str(item.get("verdict") or "").strip().lower()
            domain = str(item.get("domain") or "").strip()
            confidence = int(item.get("confidence") or 0)
            if verdict != "accept" or not domain:
                continue
            accepted.append({
                "domain": domain,
                "confidence": confidence,
                "reason": str(item.get("reason") or "").strip(),
            })
        accepted.sort(key=lambda item: item["confidence"], reverse=True)
        return accepted[:max_domains]
    except Exception as exc:
        logger.warning("Competitor LLM judge failed: %s", exc)
        return []


def build_article_brief(
    *,
    project_name: str,
    target_domain: str,
    primary_keyword: str,
    seed_keywords: list[str],
    competitor_pages: list[dict[str, Any]],
    own_pages: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not _is_configured():
        return None

    prompt = f"""
You are a senior content strategist building a research brief for a blog article.

Project name: {project_name}
Target domain: {target_domain}
Primary keyword: {primary_keyword}
Seed keywords: {json.dumps(seed_keywords)}

Own site pages:
{json.dumps(own_pages, ensure_ascii=True)}

Competitor pages from page one search results and sitemap crawl:
{json.dumps(competitor_pages, ensure_ascii=True)}

Return ONLY a JSON object with these keys:
- "search_intent": short string
- "reader_persona": short string
- "article_angle": short string
- "recommended_title": short string
- "meta_description": short string
- "content_gaps": array of 4-8 short strings describing what competitors cover that the target site should beat
- "outline": array of section objects with keys "heading" and "points" where points is an array of bullets
- "competitor_takeaways": array of 3-6 short strings
- "must_include_terms": array of 6-12 strings
"""

    try:
        payload = _chat_json(
            system_prompt="You output only valid JSON objects.",
            user_prompt=prompt,
            temperature=0.2,
        )
        return payload if isinstance(payload, dict) else None
    except Exception as exc:
        logger.warning("Article brief generation failed: %s", exc)
        return None


def write_article(
    *,
    project_name: str,
    primary_keyword: str,
    brief: dict[str, Any],
    competitor_pages: list[dict[str, Any]],
    revision_notes: list[str] | None = None,
) -> str:
    feedback_block = ""
    if revision_notes:
        feedback_block = "\nRevision notes from the auditor:\n" + "\n".join(f"- {note}" for note in revision_notes)

    prompt = f"""
Write a high-quality SEO article in Markdown.

Project: {project_name}
Primary keyword: {primary_keyword}
Brief:
{json.dumps(brief, ensure_ascii=True)}

Competitor research:
{json.dumps(competitor_pages, ensure_ascii=True)}
{feedback_block}

Requirements:
- Use the primary keyword naturally in the H1, introduction, at least one H2, and conclusion.
- Make the article original, actionable, and clearly better than the competitor pages.
- Use a strong intro, descriptive H2/H3 headings, concise paragraphs, bullets where useful, and a practical conclusion.
- Avoid making unverifiable claims about the target company.
- Output Markdown only.
"""
    return _chat_text(
        system_prompt="You are a senior SEO content writer. Output only the finished Markdown article.",
        user_prompt=prompt,
        temperature=0.35,
    )


def audit_article(
    *,
    primary_keyword: str,
    brief: dict[str, Any],
    article_markdown: str,
) -> dict[str, Any] | None:
    prompt = f"""
Audit this SEO article and grade it strictly.

Primary keyword: {primary_keyword}
Brief:
{json.dumps(brief, ensure_ascii=True)}

Article:
{article_markdown}

Return ONLY a JSON object with:
- "score": integer from 0 to 100
- "passed": boolean
- "strengths": array of short strings
- "issues": array of short strings
- "revision_notes": array of concrete rewrite instructions
Pass only if the article is excellent and deserves 90 or above.
"""
    try:
        payload = _chat_json(
            system_prompt="You are a strict SEO editor. Output only valid JSON.",
            user_prompt=prompt,
            temperature=0.1,
        )
        return payload if isinstance(payload, dict) else None
    except Exception as exc:
        logger.warning("Article audit failed: %s", exc)
        return None
