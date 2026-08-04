import json
import logging
from typing import Any

from openai import AsyncOpenAI, OpenAI

from app.config import settings

logger = logging.getLogger(__name__)

ALLOWED_KEYWORD_TYPES = {"primary", "lsi", "long-tail", "entity", "heading"}


def normalize_keyword_type(value: Any) -> str:
    keyword_type = str(value or "lsi").strip().lower().replace("_", "-")
    if keyword_type in {"longtail", "long tail"}:
        return "long-tail"
    if keyword_type in {"entities", "named-entity", "named entity"}:
        return "entity"
    if keyword_type in {"headings", "section", "section-heading"}:
        return "heading"
    if keyword_type in ALLOWED_KEYWORD_TYPES:
        return keyword_type
    return "lsi"


def _provider_config(use_writing_model: bool = False) -> tuple[str, str, str, str]:
    if settings.TOKENROUTER_API_KEY:
        model = settings.TOKENROUTER_WRITING_MODEL if use_writing_model else settings.TOKENROUTER_MODEL
        return (
            "TokenRouter",
            "https://api.tokenrouter.com/v1",
            settings.TOKENROUTER_API_KEY,
            model,
        )
    if settings.GROQ_API_KEY:
        return (
            "Groq",
            "https://api.groq.com/openai/v1",
            settings.GROQ_API_KEY,
            settings.GROQ_MODEL,
        )
    if settings.OPENROUTER_API_KEY:
        return (
            "OpenRouter",
            "https://openrouter.ai/api/v1",
            settings.OPENROUTER_API_KEY,
            settings.OPENROUTER_MODEL,
        )
    return "", "", "", ""


def is_ai_configured() -> bool:
    return bool(_provider_config()[2])


def ai_provider_name() -> str:
    return _provider_config()[0] or "AI"


def ai_generated_source() -> tuple[str, str]:
    provider = ai_provider_name()
    if provider == "Groq":
        return "https://groq.com/generated", "Groq AI"
    if provider == "OpenRouter":
        return "https://openrouter.ai/generated", "OpenRouter AI"
    return "https://ai.generated", "AI"


def _sync_client(use_writing_model: bool = False) -> OpenAI:
    _provider, base_url, api_key, _model = _provider_config(use_writing_model)
    return OpenAI(
        base_url=base_url,
        api_key=api_key,
    )


def _async_client(use_writing_model: bool = False) -> AsyncOpenAI:
    _provider, base_url, api_key, _model = _provider_config(use_writing_model)
    return AsyncOpenAI(
        base_url=base_url,
        api_key=api_key,
    )


def _strip_code_fences(content: str) -> str:
    value = (content or "").strip()
    if value.startswith("```json"):
        return value[7:-3].strip()
    if value.startswith("```"):
        return value[3:-3].strip()
    return value


def _parse_json_payload(content: str) -> Any:
    cleaned = _strip_code_fences(content)
    try:
        payload = json.loads(cleaned)
        if isinstance(payload, dict) and "data" in payload:
            return payload["data"]
        return payload
    except json.JSONDecodeError:
        # If the JSON is truncated or malformed, try to salvage any complete {...} objects
        import re
        import ast
        objects = []
        pattern = re.compile(r'\{[^{}]*\}')
        for match in pattern.finditer(cleaned):
            try:
                obj = json.loads(match.group(0))
                objects.append(obj)
            except json.JSONDecodeError:
                try:
                    obj = ast.literal_eval(match.group(0))
                    if isinstance(obj, dict):
                        objects.append(obj)
                except Exception:
                    pass
        if objects:
            return objects
        raise


async def _achat_json(
    *,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
    max_tokens: int | None = None,
    use_writing_model: bool = False,
) -> Any:
    client = _async_client(use_writing_model)
    _provider, _base_url, _api_key, model = _provider_config(use_writing_model)
    request: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
    }
    if max_tokens:
        request["max_tokens"] = max_tokens
    response = await client.chat.completions.create(
        **request,
    )
    return _parse_json_payload(response.choices[0].message.content or "")


def _chat_json(
    *,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
    max_tokens: int | None = None,
    use_writing_model: bool = False,
) -> Any:
    client = _sync_client(use_writing_model)
    _provider, _base_url, _api_key, model = _provider_config(use_writing_model)
    request: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
    }
    if max_tokens:
        request["max_tokens"] = max_tokens
    response = client.chat.completions.create(
        **request,
    )
    return _parse_json_payload(response.choices[0].message.content or "")


def _chat_text(
    *,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.3,
    max_tokens: int | None = None,
    use_writing_model: bool = False,
) -> str:
    client = _sync_client(use_writing_model)
    _provider, _base_url, _api_key, model = _provider_config(use_writing_model)
    request: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
    }
    if max_tokens:
        request["max_tokens"] = max_tokens
    response = client.chat.completions.create(
        **request,
    )
    return (response.choices[0].message.content or "").strip()


async def generate_ai_keywords(seed_keywords: list[str]) -> list[dict[str, Any]]:
    """Generate SEO keyword recommendations using the configured AI provider."""
    if not is_ai_configured():
        logger.error("AI API key not configured")
        return []

    from nlp.keywords import clean_phrase, is_publishable_keyword, seed_keyword_terms

    topic_terms = seed_keyword_terms(seed_keywords)
    prompt = f"""
You are an expert SEO keyword strategist. Use the seed keywords as the strict topic boundary.
Generate exactly 25 high-quality keyword opportunities: exactly 5 primary, 5 LSI, 5 long-tail, 5 entity, and 5 heading keywords.

Seed keywords:
{json.dumps(seed_keywords)}

Quality rules:
- Every phrase must be directly useful for the same search intent, audience, and topic cluster as the seed keywords.
- Reject bogus, random, generic, broad, off-topic, or awkward phrases.
- Do not invent fake brands, fake products, fake people, or fake entities.
- Keep phrases natural, lowercase, 2 to 6 words, and suitable for an SEO keyword table.
- Every phrase must include at least one meaningful seed keyword term exactly, so the app can safely reject unrelated junk.
- For LSI keywords, include the seed term plus a semantic modifier instead of drifting to a broad synonym-only phrase.

Type definitions:
- primary: core target phrases that match the main search intent.
- lsi: semantically related support phrases users naturally search around the topic, while still containing the seed term.
- long-tail: specific question, comparison, problem, or use-case phrases.
- entity: named concepts, categories, tools, standards, products, or recognized terms in the topic.
- heading: article section or page heading ideas that would make useful H2/H3 sections.

Return ONLY a JSON array of objects. Do not include markdown formatting, explanation, or code blocks.
Each object must have:
- "phrase": the keyword phrase (string, lowercase)
- "type": one of "primary", "lsi", "long-tail", "entity", or "heading"
"""
    try:
        payload = await _achat_json(
            system_prompt="You output only valid JSON arrays.",
            user_prompt=prompt,
            temperature=0.35,
            max_tokens=1600,
        )
        if isinstance(payload, dict) and "keywords" in payload:
            payload = payload["keywords"]
        if not isinstance(payload, list):
            return []

        valid_keywords = []
        seen_phrases: set[str] = set()
        for kw in payload:
            if isinstance(kw, dict) and kw.get("phrase"):
                phrase = clean_phrase(str(kw["phrase"]))
                kw_type = normalize_keyword_type(kw.get("type"))
                if phrase in seen_phrases:
                    continue
                if not is_publishable_keyword(phrase, min_words=2, topic_terms=topic_terms):
                    continue
                valid_keywords.append({
                    "phrase": phrase,
                    "type": kw_type,
                })
                seen_phrases.add(phrase)
        return valid_keywords
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse JSON from %s: %s", ai_provider_name(), exc)
        return []
    except Exception as exc:
        logger.error("Failed to generate keywords via %s: %s", ai_provider_name(), exc)
        return []


def filter_keyword_gap_recommendations(
    seed_keywords: list[str],
    candidates: list[dict[str, Any]],
    max_keywords: int = 60,
) -> list[dict[str, Any]]:
    """Use AI to keep and improve the strongest competitor sitemap gap keywords."""
    if not is_ai_configured():
        logger.info("AI API key not configured; skipping AI keyword gap filter")
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
- "type": one of "primary", "lsi", "long-tail", "entity", or "heading"
"""

    try:
        payload = _chat_json(
            system_prompt="You output only valid JSON arrays.",
            user_prompt=prompt,
            temperature=0.2,
            max_tokens=2200,
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
            keyword_type = normalize_keyword_type(item.get("type"))
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
        logger.error("Failed to parse JSON from %s gap filter: %s", ai_provider_name(), exc)
        return []
    except Exception as exc:
        logger.error("Failed to filter keyword gaps via %s: %s", ai_provider_name(), exc)
        return []


def judge_competitor_domains(
    seed_keywords: list[str],
    own_domain: str,
    candidates: list[dict[str, Any]],
    max_domains: int,
) -> list[dict[str, Any]]:
    """Use the LLM as the final gatekeeper for whether a domain is a true competitor."""
    if not is_ai_configured() or not candidates:
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
            max_tokens=1200,
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
    if not is_ai_configured():
        return None

    prompt = f"""
You are a master SEO content strategist building a writer-ready brief for a gap keyword article.
Your job is to identify the missing opportunity behind the keyword, synthesize competitor research, and design an article that can beat thin or generic results.

Project name: {project_name}
Target domain: {target_domain}
Gap keyword / primary keyword: {primary_keyword}
Seed keywords: {json.dumps(seed_keywords)}

Own site pages:
{json.dumps(own_pages, ensure_ascii=True)}

Competitor pages from page one search results and sitemap crawl:
{json.dumps(competitor_pages, ensure_ascii=True)}

Return ONLY a JSON object with these keys:
- "search_intent": precise string describing what the searcher wants
- "reader_persona": specific persona and sophistication level
- "article_angle": differentiated angle that directly targets the keyword gap
- "recommended_title": compelling SEO title containing the primary keyword
- "meta_description": 145-160 character description containing the primary keyword
- "content_gaps": array of 5-10 competitor weaknesses or missed subtopics to beat
- "competitor_takeaways": array of 4-8 useful patterns from competitors, without copying them
- "unique_value": array of 4-8 ways this article should be more useful than competitors
- "must_include_terms": array of 8-16 important terms, entities, and phrases
- "proof_points": array of 3-8 evidence types, examples, or caveats the writer should include without inventing facts
- "outline": array of 7-12 section objects. Each object must include "heading", "intent", and "points" where points is an array of concrete bullets.
- "faq": array of 4-8 question objects with keys "question" and "answer_angle"
- "avoid": array of 4-8 pitfalls, hallucinations, or generic claims to avoid
"""

    try:
        payload = _chat_json(
            system_prompt="You output only valid JSON objects.",
            user_prompt=prompt,
            temperature=0.2,
            max_tokens=2600,
            use_writing_model=True,
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
        feedback_block = (
            "\nThe previous draft failed the quality audit. Solve every problem below by rewriting the full article, "
            "then return only the improved finished article. Do not mention these notes.\n"
            + "\n".join(f"- {note}" for note in revision_notes)
        )

    prompt = f"""
Write a master-level SEO article in Markdown for the exact gap keyword.

Project: {project_name}
Gap keyword / primary keyword: {primary_keyword}
Strategic brief:
{json.dumps(brief, ensure_ascii=True)}

Competitor research:
{json.dumps(competitor_pages, ensure_ascii=True)}
{feedback_block}

Requirements:
- Output only the finished Markdown article. No notes, no code fences, no meta commentary.
- Length: write at least 1,100 words and usually 1,200-1,800 words. Do not stop at a short overview.
- Use exactly one H1. The H1 must include the primary keyword naturally.
- The introduction must answer the search intent quickly and make clear why the article is useful.
- Use descriptive H2/H3 sections that follow the brief outline and directly cover the gap keyword.
- Include at least seven useful H2 sections, including an FAQ/common questions section.
- Expand each major H2 with concrete explanation, examples, decision criteria, or practical steps. Avoid one-paragraph sections.
- Beat the competitor pages by adding clearer explanations, practical examples, decision criteria, mistakes to avoid, and a useful FAQ.
- Include the primary keyword naturally in the introduction, at least one H2, body copy, and conclusion. Do not keyword-stuff.
- Use must-include terms when they fit naturally.
- Add a concise table, checklist, or step-by-step framework when it helps the reader decide or act.
- Synthesize competitor research; do not copy wording, structure, or claims.
- Do not invent statistics, dates, prices, customers, features, certifications, or claims about the target company.
- If evidence is missing, phrase carefully and explain how the reader can evaluate it.
- Keep paragraphs tight, concrete, and expert. Avoid filler, generic motivational language, and obvious definitions unless needed.
- End with a useful conclusion that reinforces the primary keyword and next step.
"""
    return _chat_text(
        system_prompt=(
            "You are a world-class SEO strategist, subject-matter ghostwriter, and ruthless editor. "
            "You write practical, source-grounded articles that satisfy search intent and outperform generic competitor content."
        ),
        user_prompt=prompt,
        temperature=0.28,
        max_tokens=4500,
        use_writing_model=True,
    )


def audit_article(
    *,
    primary_keyword: str,
    brief: dict[str, Any],
    article_markdown: str,
) -> dict[str, Any] | None:
    prompt = f"""
Audit this SEO article as a demanding SEO editor. Grade whether it deserves to be published for the exact gap keyword.

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
- "missing_sections": array of missing sections or angles
- "keyword_intent_score": integer from 0 to 100
- "gap_coverage_score": integer from 0 to 100

Evaluation rules:
- Pass only if score is 92 or above, keyword_intent_score is 90 or above, and gap_coverage_score is 90 or above.
- If not passed, revision_notes must tell the writer exactly how to rewrite the full article so the next version can pass.
- Fail thin, generic, fluffy, or off-topic drafts even if the prose is clean.
- Fail drafts that do not clearly target the primary keyword.
- Fail drafts that invent unsupported facts or make unverifiable claims.
- Reward practical depth, source-grounded synthesis, clear structure, and competitor-gap coverage.
"""
    try:
        payload = _chat_json(
            system_prompt="You are a strict SEO editor. Output only valid JSON.",
            user_prompt=prompt,
            temperature=0.1,
            max_tokens=1800,
        )
        return payload if isinstance(payload, dict) else None
    except Exception as exc:
        logger.warning("Article audit failed: %s", exc)
        return None
