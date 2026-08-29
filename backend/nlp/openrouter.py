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
    if settings.DEEPSEEK_API_KEY:
        return (
            "DeepSeek",
            "https://api.deepseek.com",
            settings.DEEPSEEK_API_KEY,
            settings.DEEPSEEK_MODEL,
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
    return "https://ai.generated", "AI Recommendations"


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

    try:
        response = client.chat.completions.create(**request)
        return response.choices[0].message.content or ""
    except Exception as e:
        import openai
        if isinstance(e, openai.RateLimitError) and not use_writing_model:
            logger.warning(f"Groq Rate limit hit. Falling back to OpenRouter for this request.")
            # Fallback to the writing model (OpenRouter)
            client = _sync_client(use_writing_model=True)
            _provider, _base_url, _api_key, model = _provider_config(use_writing_model=True)
            request["model"] = model
            response = client.chat.completions.create(**request)
            return response.choices[0].message.content or ""
        raise e


_semantic_cache = {}

async def generate_core_domain_terms(target_keywords: list[str], audit_summary: str | None = None) -> dict[str, list[str]]:
    """
    Generate dynamic Core Domain Terms and Generic Terms for upstream semantic filtering.
    """
    from .openrouter import is_ai_configured, _achat_json
    import json
    
    if not is_ai_configured() or not target_keywords:
        return {"core_terms": [], "generic_terms": [], "negative_terms": []}

    cache_key = json.dumps(target_keywords)
    if cache_key in _semantic_cache:
        return _semantic_cache[cache_key]

    prompt = f"""
You are an expert SEO taxonomist and NLP analyzer. 
I have a website defined by these Seed Keywords: {json.dumps(target_keywords)}
And this Context/Audit Summary:
{audit_summary or "No summary provided. Rely solely on seed keywords."}

Your task is to analyze the semantic core of this website and break it down into three distinct JSON arrays to be used as a Python stopword/gate filter.

1. "core_terms": A comprehensive array of the core domain entities, including synonyms, closely related niches, and semantic variations. (e.g., if the seed is "circuit diagram maker", the core terms are "circuit", "wiring", "electronics", "electric", "schematic", "pcb"). Limit to max 30 terms.
2. "generic_terms": An array of generic modifiers that often appear in keywords but DO NOT define the niche (e.g., "diagram", "software", "maker", "tool", "app", "system", "calculator"). Limit to max 30 terms.
3. "negative_terms": An array of terms representing 3rd-party drift (e.g. "jira", "sharepoint", "trello") or distinctly unrelated niches that might mistakenly overlap (e.g. "volcano", "muscular", "urinary"). Limit to max 20 terms.

Ensure all terms are lowercase strings.
Do not output anything except valid JSON matching this schema:
{{
  "core_terms": ["..."],
  "generic_terms": ["..."],
  "negative_terms": ["..."]
}}
"""
    try:
        payload = await _achat_json(
            system_prompt="You output only valid JSON.",
            user_prompt=prompt,
            temperature=0.1,
            max_tokens=2000,
        )
        if isinstance(payload, dict):
            # Ensure we only have single words
            def _extract_words(term_list):
                words = set()
                for term in term_list:
                    for w in str(term).lower().replace("-", " ").split():
                        w = ''.join(c for c in w if c.isalnum())
                        if len(w) > 1:
                            words.add(w)
                return list(words)
                
            res = {
                "core_terms": _extract_words(payload.get("core_terms", [])),
                "generic_terms": _extract_words(payload.get("generic_terms", [])),
                "negative_terms": _extract_words(payload.get("negative_terms", []))
            }
            _semantic_cache[cache_key] = res
            return res
    except Exception as exc:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning("generate_core_domain_terms failed: %s", exc)
        
    return {"core_terms": [], "generic_terms": []}


def verify_cluster_intent(cluster: list[dict]) -> dict:
    """
    Verifies a tight (Level-2) cluster. Returns one of:
      {"verdict": "same_intent"}                      -> Tier 1 (merge)
      {"verdict": "related_nuance"}                   -> Tier 2 (subheading group)
      {"verdict": "different", "groups": [[...],[...]}} -> split, re-classify each group
    """
    if len(cluster) < 2:
        return {"verdict": "same_intent"}

    phrases = [kw["phrase"] for kw in cluster]

    prompt = f"""[SYSTEM COMMAND — INTENT CLUSTER VERIFICATION]

You are an SEO search-intent auditor. These keywords were flagged as very similar in
meaning by an automated similarity check:

{json.dumps(phrases)}

Classify this group into exactly ONE of three verdicts:

1. "same_intent" — these are genuinely the SAME searcher intent (same goal, same
   audience, same journey stage), just phrased differently. They should become ONE
   page targeting ONE of these phrases.

2. "related_nuance" — these are closely related and could reasonably live on ONE
   comprehensive article, but each phrase represents a slightly distinct angle or
   sub-question worth its own section (H2/H3) within that article — not distinct
   enough to deserve fully separate pages.

3. "different" — at least one keyword here represents a meaningfully different
   intent (different audience, different goal, or different journey stage) and
   should NOT be grouped with the others at all.

**Examples:**
- "iron condor vs iron butterfly" / "iron butterfly vs iron condor" -> same_intent (word-order flip)
- "iron condor risk management" / "0dte iron condor risk management" / "0dte risk management" -> related_nuance (one is broader than the other two, all valid sections of one guide)
- "cash secured put strategy" / "cash secured put nvidia strategy" -> different (general vs ticker-specific — different searcher intent)

**Output rules:**
- If verdict is "same_intent" or "related_nuance", return: {{"verdict": "same_intent"}} or {{"verdict": "related_nuance"}}
- If verdict is "different", return: {{"verdict": "different", "groups": [["phrase1","phrase2"], ["phrase3"]]}}
  Every input phrase must appear in exactly one output group. Do not add, drop, or rewrite phrases.

Return ONLY the JSON object, nothing else.
"""
    try:
        result = _chat_json(
            system_prompt="You output only valid JSON objects.",
            user_prompt=prompt,
            temperature=0.1,
            max_tokens=500,
        )
        if isinstance(result, dict) and "verdict" in result:
            return result
        return {"verdict": "related_nuance"}
    except Exception as e:
        logger.warning("verify_cluster_intent LLM call failed: %s", e)
        return {"verdict": "related_nuance"}


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
- Every keyword MUST be highly semantically relevant to the primary seed keywords.
- Absolutely NO unrelated keywords, hallucinated terms, or irrelevant BS.
- If a keyword does not directly relate to the user intent of the seed keyword, discard it.
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
        
        if valid_keywords:
            import asyncio
            filtered = await asyncio.to_thread(
                filter_keyword_gap_recommendations,
                seed_keywords,
                valid_keywords,
                25
            )
            # Ensure phrase fallback
            for kw in filtered:
                if not kw.get("phrase") and kw.get("source_phrase"):
                    kw["phrase"] = kw["source_phrase"]
                if not kw.get("phrase"):
                    continue
            return [kw for kw in filtered if kw.get("phrase")]
        return []
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse JSON from %s: %s", ai_provider_name(), exc)
        return []
    except Exception as exc:
        logger.error("Failed to generate keywords via %s: %s", ai_provider_name(), exc)
        return []


def generate_ai_keywords_sync(seed_keywords: list[str]) -> list[dict[str, Any]]:
    """Synchronous version of generate_ai_keywords for background worker pipelines."""
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
- Every keyword MUST be highly semantically relevant to the primary seed keywords.
- Absolutely NO unrelated keywords, hallucinated terms, or irrelevant BS.
- If a keyword does not directly relate to the user intent of the seed keyword, discard it.
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
        payload = _chat_json(
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
        
        if valid_keywords:
            filtered = filter_keyword_gap_recommendations(
                seed_keywords,
                valid_keywords,
                25
            )
            if not filtered:
                return []
            # Ensure phrase fallback
            for kw in filtered:
                if not kw.get("phrase") and kw.get("source_phrase"):
                    kw["phrase"] = kw["source_phrase"]
                if not kw.get("phrase"):
                    continue
            return [kw for kw in filtered if kw.get("phrase")]
        return []
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse JSON from %s: %s", ai_provider_name(), exc)
        return []
    except Exception as exc:
        logger.error("Failed to generate keywords via %s: %s", ai_provider_name(), exc)
        return []


def extract_keywords_from_urls_ai(
    seed_keywords: list[str],
    urls: list[Any],
    topic_terms: set[str] | None = None,
    negative_terms: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Uses LLM to intelligently extract SEO keywords from competitor URL slugs."""
    if not is_ai_configured() or not urls:
        return []

    from nlp.keywords import clean_phrase, is_publishable_keyword, seed_keyword_terms
    if not topic_terms:
        topic_terms = seed_keyword_terms(seed_keywords)
    
    all_results = []
    chunk_size = 100
    
    for i in range(0, len(urls), chunk_size):
        chunk = urls[i:i + chunk_size]
        url_payload = [{"id": str(u.id), "url": u.url} for u in chunk]
        
        prompt = f"""
[SYSTEM COMMAND — URL KEYWORD EXTRACTION]
You are an expert SEO data analyst.
Seed topic: {json.dumps(seed_keywords)}

I will provide a JSON array of competitor URLs.
Your job is to read the URL slugs and intelligently INFER the exact core SEO keywords those pages are targeting.

Rules:
- You must ONLY extract keywords that are highly relevant to the seed topic. Discard completely unrelated URLs.
- Normalize keywords to a natural search phrase (lowercase, 2 to 6 words). DO NOT just output a hyphenated slug.
- You must include the exact UUIDs of the URLs that target each keyword in the "url_ids" array.
- "type" should be one of: primary, lsi, long-tail, entity.

Input URLs:
{json.dumps(url_payload, ensure_ascii=False)}

Return ONLY a JSON array of objects. Do not include markdown or explanations.
Example output format:
[
  {{
    "phrase": "circuit diagram maker",
    "type": "primary",
    "url_ids": ["uuid-1", "uuid-2"]
  }}
]
"""
        try:
            payload = _chat_json(
                system_prompt="You output only valid JSON arrays.",
                user_prompt=prompt,
                temperature=0.1,
                max_tokens=2500,
            )
            if isinstance(payload, dict) and "keywords" in payload:
                payload = payload["keywords"]
            if not isinstance(payload, list):
                continue
                
            for item in payload:
                if not isinstance(item, dict):
                    continue
                phrase = clean_phrase(str(item.get("phrase", "")))
                if not is_publishable_keyword(phrase, min_words=2, topic_terms=topic_terms, negative_terms=negative_terms):
                    continue
                    
                kw_type = normalize_keyword_type(item.get("type"))
                url_ids = item.get("url_ids", [])
                if not isinstance(url_ids, list):
                    continue
                    
                valid_ids = [uid for uid in url_ids if isinstance(uid, str)]
                if valid_ids:
                    all_results.append({
                        "phrase": phrase,
                        "type": kw_type,
                        "url_ids": valid_ids
                    })
        except Exception as exc:
            logger.error("AI URL extraction failed for chunk: %s", exc)
            continue

    return all_results


async def generate_ai_top_picks(seed_keywords: list[str], existing_keywords: list[str]) -> list[dict[str, Any]]:
    """Generate a curated list of the absolute top 5 best keywords using the configured AI provider, from existing keywords."""
    if not is_ai_configured():
        logger.error("AI API key not configured")
        return []

    from nlp.keywords import clean_phrase, is_publishable_keyword, seed_keyword_terms

    topic_terms = seed_keyword_terms(seed_keywords)
    prompt = f"""
You are an expert SEO keyword strategist. 
You are provided with a list of already found keywords. Your task is to select the absolute best 5 to 10 keywords STRICTLY FROM THIS LIST that are highly relevant to the seed keywords.
These should be the "Top Picks" - high intent, strong relevance, and maximum SEO value.

Seed keywords:
{json.dumps(seed_keywords)}

Existing keywords (choose ONLY from these):
{json.dumps(existing_keywords)}

Quality rules:
- Every selected phrase MUST exactly match a phrase from the Existing keywords list. Do NOT invent new phrases.
- Every keyword MUST be highly semantically relevant to the primary seed keywords.
- Absolutely NO unrelated keywords, hallucinated terms, or irrelevant BS.

Return ONLY a JSON array of objects. Do not include markdown formatting, explanation, or code blocks.
Each object must have:
- "phrase": the exact keyword phrase from the list (string, lowercase)
- "type": one of "primary" or "long-tail"
"""
    try:
        payload = await _achat_json(
            system_prompt="You output only valid JSON arrays.",
            user_prompt=prompt,
            temperature=0.35,
            max_tokens=600,
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
        logger.error("Failed to generate top picks via %s: %s", ai_provider_name(), exc)
        return []


def filter_keyword_gap_recommendations(
    seed_keywords: list[str],
    candidates: list[dict[str, Any]],
    audit_summary: str | None = None,
    max_keywords: int = 60,
) -> list[dict[str, Any]] | None:
    """Uses LLM to aggressively filter and deduplicate keyword gap candidates."""
    if not is_ai_configured() or not candidates:
        return None

    trimmed_candidates = candidates[: settings.AI_KEYWORD_GAP_CANDIDATE_LIMIT]
    
    audit_context = f"""
**AGENT AUDIT SUMMARY (GOLD HUNTER)**
{audit_summary}

**NEW AUDIT-BASED RULES:**
1. Extract the Core Subject, Core Audience, and Core Action from the Agent Audit Summary.
2. Apply the Hard Block Rules: Reject any keyword or topics outside the Core Subject.
3. Keep only keywords that serve the Core Audience and enable the Core Action.
""" if audit_summary else ""

    prompt = f"""
[SYSTEM COMMAND — FINAL KEYWORD SANITY FILTER]
{audit_context}
You are a Keyword Sanity Filter. You have received a raw list of keywords extracted from competitor sitemaps.

**Step 0: NATURAL LANGUAGE NORMALIZATION (CRITICAL)**
For every raw keyword, rewrite it into a natural human search query:
- Reverse awkward structures: "board games using spin wheel" → "spin the wheel board game".
- Remove redundant words: "games using spin wheel" → "spin the wheel games".
- Use common search patterns: "spin wheel for instagram" → "instagram spin wheel".
- Prioritize shorter, standard collocations (3-4 words) over longer descriptive phrases.
- If the normalized query sounds unnatural, rewrite it again until it passes the "Would a real human type this?" test.

**Step 1: TOPICAL NEIGHBORHOOD & STRICT SEED RELEVANCE (CRITICAL)**
Compare the normalized query against the seed keyword set: {json.dumps(seed_keywords)}
Is this query semantically within 1-2 hops of the seed keywords, or is it 3+ hops away? If it is beyond the immediate topical neighborhood of the exact seed, it MUST be DISCARDED.
If the query does NOT directly support, align with, or fall under the exact mechanical use-cases of the seed keywords, REJECT IT IMMEDIATELY. Aggressively reject:
- Generic umbrella terms that are too broad.
- Tangential topics (e.g., if the seed is "lunar age calculator", reject "chinese new year traditions").
- Other categories in the same broad niche (e.g., if the seed is "circuit diagram", reject "fishbone diagram", "network diagram", or other unrelated diagram types).
- Completely unrelated niches.

**Step 2: ANTI-CANNIBALIZATION & DEDUPLICATION (CRITICAL)**
Look at all the keywords that passed Step 1. Many competitors use slightly varied phrases for the exact same search intent (e.g. "circuit diagram tutorial for beginners" vs "understanding circuit diagrams for beginners").
- Group all variations that share the exact same search intent.
- Keep ONLY ONE normalized, best-representing keyword per intent.
- DISCARD the redundant variations. Do NOT allow multiple keywords with the same intent to pass.

**Step 3: Volume Gate**
- For the normalized query, estimate monthly search volume.
- Keep if 500+ per month.
- Reject if below 500.

**Step 4: Final Output**
- Return ALL deduplicated keywords that passed Steps 1-3 (maximum {max_keywords} total).
- Return ONLY a JSON array of objects. Do not include markdown formatting or explanations.
- Each returned object must include:
  - "source_phrase": exact original phrase from the candidates
  - "phrase": the normalized search query
  - "volume": Estimated volume (High/Medium/Low)
  - "type": one of "primary", "lsi", "long-tail", "entity", or "heading"

Candidates:
{json.dumps(trimmed_candidates, ensure_ascii=True)}
"""

    try:
        payload = _chat_json(
            system_prompt="You output only valid JSON arrays.",
            user_prompt=prompt,
            temperature=0.1,
            max_tokens=2500,
        )
        if isinstance(payload, dict) and "keywords" in payload:
            payload = payload["keywords"]
        if not isinstance(payload, list):
            return None

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
            volume = str(item.get("volume") or "")
            if not source_phrase and phrase in candidate_phrases:
                source_phrase = phrase
            if not source_phrase or source_phrase not in candidate_phrases or not phrase:
                continue
            valid.append({
                "source_phrase": source_phrase,
                "phrase": phrase,
                "type": keyword_type,
                "volume": volume,
            })
            if len(valid) >= max_keywords:
                break

        return valid
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse JSON from %s gap filter: %s", ai_provider_name(), exc)
        return None
    except Exception as exc:
        logger.error("Failed to filter keyword gaps via %s: %s", ai_provider_name(), exc)
        return None


def judge_competitor_domains(
    seed_keywords: list[str],
    own_domain: str,
    candidates: list[dict[str, Any]],
    audit_summary: str | None = None,
    max_domains: int = 25,
) -> list[dict[str, Any]] | None:
    """Use the LLM as the final gatekeeper for whether a domain is a true competitor."""
    if not is_ai_configured() or not candidates:
        return []

    audit_context = f"""
**AGENT AUDIT SUMMARY (GOLD HUNTER)**
{audit_summary}

**NEW AUDIT-BASED RULES:**
1. Extract the Core Subject, Core Audience, and Core Action from the Agent Audit Summary.
2. Apply the Hard Block Rules: Reject sites that do not fit these criteria and are not thematically relevant for our Core Subject, Core Audience, and Core Action.
""" if audit_summary else ""

    prompt = f"""
You are the final competitor judge for an SEO SaaS.
{audit_context}

Target site:
{own_domain}

Primary keyword set:
{json.dumps(seed_keywords)}

Candidate competitors:
{json.dumps(candidates, ensure_ascii=True)}

Choose only domains that are true business/search competitors for the target site. 
Reject dictionaries, marketplaces, social networks, forums, docs portals, and generic informational sites.
STRICT TOPICAL NICHE MATCH: You must aggressively reject any domain that belongs to a broader industry or different topical niche. 
- If the target site is a dedicated micro-tool, localized business, or specialized service (like a specific calculator or trading strategy site), you MUST completely REJECT broad software tutorial blogs (e.g., Excel/Google Sheets blogs), generic IT/tech support sites, and generic directories.
- Only accept domains that are DIRECT, dedicated competitors offering the same specific service/niche.

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


def write_prompt(
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
            "\nThe previous generated prompt failed the audit. Fix these issues by providing an improved Master Prompt:\n"
            + "\n".join(f"- {note}" for note in revision_notes)
        )

    # Build Outline
    outline_lines = []
    outline_lines.append(f"H1: {primary_keyword.title()}")
    for section in brief.get("outline", []):
        heading = section.get("heading", "")
        # Assuming main sections are H2s
        outline_lines.append(f"H2: {heading}")
        for point in section.get("points", []):
            outline_lines.append(f"- {point}")
    outline_str = "\n".join(outline_lines)

    # Build Entities
    entities_list = brief.get("must_include_terms", [])
    entities_str = ", ".join(entities_list) if entities_list else "None provided"

    # Build Competitor Content
    comp_content_lines = []
    for page in competitor_pages:
        url = page.get("url", "Unknown URL")
        content = page.get("content", "")
        comp_content_lines.append(f"<hr/><p><em>--- Extracted from: {url} ---</em></p>\n\n{content}\n")
    competitor_content_str = "\n".join(comp_content_lines)

    template = f"""# CONTENT WRITING ASSIGNMENT

## PRIMARY KEYWORD
"{primary_keyword}"

---

# ARTICLE STRUCTURE

## Heading Outline (Follow this structure exactly)
{outline_str}

---

# SEMANTIC OPTIMIZATION

## Entities to Include
Use these entities naturally throughout the content:
{entities_str}

## Key Phrases (N-Grams)
### AI-Selected Priority Phrases (USE THESE FIRST)
None selected

### AI-Generated Phrases
{entities_str}

### Unique N-Grams (Stand Out Phrases)
{entities_str}

### Competitor Phrases (Optional)
None extracted

## NLP Keywords (Topic Vocabulary)
{entities_str}

## Skip-Gram Dominant Word Pairs
These word pairs frequently appear together when discussing this topic:
None provided

---

# SEO GUIDELINES

## SEO Optimization Rules
Do not distance the question from the answer.
Example: For "How much caffeine is in coffee?" immediately answer, "There is 95 mg of caffeine in coffee." then elaborate.
Explanation: Answer the question right away to provide clarity, then give details.
Do not delay the answer.
Question: What are the benefits of Charts for entrepreneurs?
Wrong Structure: Charts are the main element for... To prepare a Chart.... Benefits of Charts,....
Correct Structure: There are X main benefits of a Chart for an entrepreneur....
Singularity and Plurality matter for micro semantics.
Don't Use Analogies. An analogy is a way of explaining something by comparing it to something else that is similar. It's like saying one thing is similar to another to help people understand a concept better. Avoid using analogies as they can confuse search engines and reduce clarity.
Avoid coreference errors. Improper pronoun usage may result in a "coreference error." This error happens when search engines struggle to understand which noun or entity the pronoun is referring to.
Example of a Coreference Error: "Joe Rogan did a podcast with Elon Musk, and he shared his thoughts on finance and law."
In this case, it's unclear who shared their thoughts—Joe Rogan or Elon Musk? Since the pronoun "he" doesn't clearly refer to a specific entity, Google may get confused while processing the sentence.
Google will attempt to resolve this ambiguity by searching for co-occurrences of both entities on the web. However, such confusion signals to Google that the article may not be well-structured or carefully written.
Don't create an extra sentence if there is no logical reason.
Example: How old is Tanjiro in Demon Slayer anime?
Answer 1: Tanjiro is 25 years old. His birthdate is Dec 2, 2002.
Answer 2: Tanjiro is 25 years old and his birthdate is Dec 2, 2002.
Answer 3: Tanjiro is 25 years old. Tanjiro's birthdate is Dec 2, 2002.
Answer 2 is best because with each new sentence search engines will use a new token. Both Answer 1 and Answer 3 will require two tokens, but Answer 2 will require only 1 token.
Always Use the Abbreviation in Parentheses on First Mention.
When you introduce an entity or concept for the first time, include its abbreviation in parentheses right after the full term. This way, readers immediately know what the abbreviation stands for, making it easier to follow the content if the abbreviation is used later.
Incorrect: "Bitcoin is the main cryptocurrency asset."
Correct: "Bitcoin (BTC) is the main cryptocurrency asset for crypto trading platforms."
Do not send the reader, or the text processors to the back of the article.
Do not send the reader by saying "As stated before", or "As it is explained in the Y section".
Wrong Structure: "As it is shown in the article, the most dangerous poisons in the world have been determined by the P method."
Correct Structure: "The most dangerous poisons in the world have been determined by the P Method."
Explanation: Instead of directing readers back to a previous section, restate the information directly. This keeps the content flow uninterrupted and makes it easier for readers to follow without needing to recall previous sections.
Give Safe Answers.
Question: "Does laser cutting produce clean and precise edges compared to other cutting methods?"
Answer: Yes, laser cutting produces clean and precise edges compared to other cutting methods, such as X, Y, and Z. The cleanness and precision of edges during laser cutting are affected by five main factors: X, Y, Z, D…. These factors increase their weight under the conditions of X, Y, Z.
A Laser Cutter industrial user experiences… according to …..
A Laser Cutter manufacturer, X, conveys Y in their Z paper….
A Laser Cutter observation from 2017 during the construction of …. involves ……
Bold the answer, not the search term.
Query: What is a Penguin?
Answer: <b>A penguin is a flightless seabird.</b>
Answer: A penguin is <b>a flightless seabird.</b>
Signal the answer part, not the relevance.
Put the "if" statements in the second part of the sentence.
"If A becomes B, do X." → Less preferred
"Do X, if A becomes B." → Better
State what to do first, then explain the condition.
"If it rains, take an umbrella." → Less preferred
"Take an umbrella, if it rains." → Better
Optimize Subordinate Text First Sentence.
Heading: How to do X...
Wrong Supporting Text: X is....
Correct Supporting Text: To do X....

Match the Adjectives, Predicates, Nouns Order Between Questions and Answers.
For clarity and cohesion, keep the structure of adjectives, predicates, and nouns in the same order in both the question and answer.
Question: "What are effective focus-improving techniques?"
Answer: "Effective focus-improving techniques include setting goals, reducing multitasking, and taking breaks."
Give examples after a plural noun.
"There are 40 different cryptocurrencies to trade on Coinbase, including Bitcoin and Ethereum."
Food Options: There are 25 delicious dishes to try at the restaurant, including pasta, sushi, and tacos.
Workout Types: There are 15 types of workouts available in the app, including yoga, HIIT, and strength training.
Languages Offered: There are 20 languages you can learn on the platform, including Spanish, Mandarin, and Arabic.
Understand Context of Verbs.
'Increase' signals 'health' (measurable metrics, quantities, or intensities).
Example: "Consistent stretching can increase flexibility over time."

'Improve' signals 'skill' + 'health' (skills or health outcomes that can be enhanced).
Example: "Practicing regularly will improve your language proficiency."

'Develop' signals 'skill' (gradual skill acquisition or growth in processes).
Example: "Working in a startup environment helps employees develop resilience and adaptability."

Determine predicates wisely.
Be Specific When Describing Things.
Do not tell "The symptoms of X disease...".
Tell, "There are 6 severe symptoms of X disease, these are... There are 9 rare symptoms of X disease..."
Experts are specific.

General vs. Expert-Like Examples:
Condition Explanation:
General: "The symptoms of malaria include fever, chills, and nausea."
Expert-Like: "Malaria has 4 primary symptoms, which are fever, chills, headache, and nausea. Additionally, there are 3 rare symptoms: confusion, seizures, and bleeding."

Product Benefits:
General: "The benefits of Product Y are numerous."
Expert-Like: "Product Y offers 5 key benefits: X, Y, Z..."
Use Numeric Values.
Do not tell "There are many reasons...".
Tell, "There are 5 main reasons...".
Experts are specific. Always quantify when possible.
Cut the Fluff out. Delete all contextless words.
Wrong: "There is one more fact about electric cars that every driver should know, and it is the electric charger capacity. Also, According to the electric charger type, the electric battery charging time might vary."
Correct: "Electric car charging time changes based on electric car charger type. For example, X type car charger is observed to be faster 5% compared to Y type of electric car charger."
Remove words like: "Also", "According to the", "should know", "might", "There is one more fact", "it is the".
Be Certain.
"Sun will rise tomorrow" → Wrong. A limit on how certain we can be because it depends on time and uses the wrong form. (It's just a possibility)
"Sun rises every day." → Correct. A fact.
Knowledge should be certain and definite. State facts, not possibilities.
Use the same Part of Speech Tag (Word Role) in the first word of the sentence for a listing.
If starting with a verb + noun structure:
- Ensure proper alignment.
- Clear unnecessary clutter.
- Spend time reviewing details.
- Absorb useful information.

Alternatively, if starting with a noun:
- Coffee provides energy and antioxidants.
- Exercise boosts metabolism and strengthens muscles.
- Hydration improves skin and aids digestion.

Using a consistent part of speech, especially at the beginning of list items, makes the list easier to follow and more visually appealing. It also reinforces a structured, intentional tone, which is helpful for both readability and SEO.
Prioritize Attributes and Contexts.
Interrogative Term: Where is a signal for place.
Query: "Where does a Penguin Live?"
Answer: "Penguins live below the equator, in the X, Y, Z geographies because their flippers and flightless seabirds nature provide..."
Match the context of the question in your answer. Where questions need location answers first.
If you're mentioning measurement units in your content, always try to mention more and diverse measurement units.
Less measurement units: "For each pound lost, drink around 16-20 oz of water."
More measurement units: "For each pound (0.45 kg) lost, drink around 16-20 oz (0.5-0.6 liters) of water."
The second sentence is more enriched with information and has more connection to different types of related entities, i.e., kg and liters.
From the user experience point of view, the second sentence is more helpful for users as well, because different users process information with different mindsets.
Thus, more units help to satisfy a more diverse and relevant target user class.
Boolean Questions should start with Yes or No.
Question: "Does Water In Food Help When Drinking Water Is Restricted?"
Answer: "Yes, eating food high in water content that is easily digestible helps with overall fluid intake when drinking water is restricted.
According to Wiseman, digesting fat is the hardest and requires a lot of water.
The Federal Emergency Management Agency (FEMA) recommends not eating salty foods as they can increase thirst."
Start with a clear Yes or No, then elaborate with supporting details.

## Writing Style Instructions
Omit needless words. Vigorous writing is concise. A sentence should contain no unnecessary words, a paragraph no unnecessary sentences, for the same reason that a drawing should have no unnecessary lines and a machine no unnecessary parts. This requires not that the writer make all their sentences short, or that they avoid all detail and treat their subjects only in outline, but that they make every word tell.

Use the active voice. Prefer concrete, physical language and analogies.
Use simple language: Write plainly with short sentences.

Example: "I need help with this issue."

Avoid AI-giveaway phrases: Don't use clichés like "dive into," "unleash your potential," etc.

Avoid: "Let's dive into this game-changing solution."

Use instead: "Here's how it works."

Be direct and concise: Get to the point; remove unnecessary words.

Example: "We should meet tomorrow."

Maintain a natural tone: Write as you normally speak; it's okay to start sentences with "and" or "but."

Example: "And that's why it matters."

Avoid marketing language: Don't use hype or promotional words.

Avoid: "This revolutionary product will transform your life."

Use instead: "This product can help you."

Keep it real: Be honest; don't force friendliness.

Example: "I don't think that's the best idea."

Simplify grammar: Don't stress about perfect grammar; it's fine not to capitalize "i" if that's your style.

Example: "i guess we can try that."

Stay away from fluff: Avoid unnecessary adjectives and adverbs.

Example: "We finished the task."

Focus on clarity: Make your message easy to understand.

Example: "Please send the file by Monday."
Use clear, natural human language and avoid overused words or phrases. Do not use terms like as an AI language model or avoid, it's critical to, or tapestry (unless needed). Avoid expressions such as it's important to note, I hope this email finds you well, crucial, or certainly. Also, skip transitional phrases like in summary, remember that, furthermore, additionally, specifically, consequently, importantly, indeed, notably, despite, essentially, alternatively, also, even though, because, in contrast, although, due to, given that, arguably, you may want to, on the other hand, as previously mentioned, it's worth noting that, to summarize, ultimately, or to put it simply. Do not include action words like navigating, dive, tailored, embark, unlock the secrets, unveil the secrets, elevate, unleash, harness, delve into, take a dive into, mastering, excels, imagine, enhance, emphasise/emphasize, revolutionize, foster, subsequently, whispering, reverberate, or promptly. Avoid adjectives such as meticulous, complexities, realm, understanding, everchanging, ever-evolving, daunting, cutting-edge, robust, power, tapestry, bustling, vibrant, metropolis, crucial, essential, vital, keen, fancy, labyrinth, gossamer, enigma, or indelible. Keep responses in detail, clear, human-like. Avoid use of complex robotic sentences.

---

# INTRODUCTION WRITING INSTRUCTIONS

## Purpose
Summarize the whole document (heading vectors) in a representative way by following the same order.

## Instructions for Introduction

### 1. Implicit Definition
Provide an implicit definition of "{primary_keyword}" and explain how it works in a representative way

### 2. Main Benefits
Highlight the main benefits of "{primary_keyword}"

### 3. Main Uses
Describe the main uses and applications of "{primary_keyword}"

### 4. Main Parts/Components
Outline the main parts or components of "{primary_keyword}"

## Best Practices
- Use the same n-grams in both the introduction (intro) and conclusion (outro)
- Ensure the introduction mirrors the document structure
- Keep the introduction concise but comprehensive

---

# COMPETITOR CONTENT ANALYSIS

## Full Competitor Content Reference
Study this complete competitor content for comprehensive analysis:

\"\"\"
{competitor_content_str}
\"\"\"

Analyze and incorporate:
- The writing tone (formal, casual, conversational)
- Sentence structure and length patterns
- How topics are introduced and explained
- Content flow and transitions
- Key points and arguments made
- Structure and organization
- Unique angles and perspectives

BEGIN WRITING THE ARTICLE NOW:
"""

    prompt = f"""
You are an expert Prompt Engineer.
Your ONLY job is to output the exact Master Prompt template provided below.
DO NOT add any conversational filler. DO NOT put it inside markdown code blocks (like ```).
Just output the raw Master Prompt text exactly as it is formatted.
{feedback_block}

TEMPLATE TO OUTPUT:
{template}
"""
    return _chat_text(
        system_prompt="You are a strict text formatter. Output only the requested text exactly as specified.",
        user_prompt=prompt,
        temperature=0.0,
        max_tokens=4500,
        use_writing_model=False,
    )


def audit_prompt(
    *,
    prompt_markdown: str,
) -> dict[str, Any] | None:
    prompt = f"""
Audit this Master Prompt to ensure it contains all necessary sections and formatting.

Prompt to audit:
{prompt_markdown}

Verify the following:
1. It must start with "# CONTENT WRITING ASSIGNMENT".
2. It must have a "## PRIMARY KEYWORD" section.
3. It must have an "# ARTICLE STRUCTURE" section with an outline.
4. It must have an "# SEO GUIDELINES" section.
5. It must have an "# INTRODUCTION WRITING INSTRUCTIONS" section.
6. It must end with "BEGIN WRITING THE ARTICLE NOW:".

Return ONLY a JSON object with these exact keys:
- "score": 0 to 100 integer. 100 means perfect prompt structure.
- "passed": boolean true if it has all required sections.
- "strengths": array of 1-3 strings.
- "issues": array of missing sections or formatting errors (if any).
- "revision_notes": array of concrete instructions to fix the prompt (if any).
"""
    try:
        payload = _chat_json(
            system_prompt="You are a strict auditor. You output only valid JSON objects.",
            user_prompt=prompt,
            temperature=0.0,
            max_tokens=800,
            use_writing_model=False,
        )
        return payload if isinstance(payload, dict) else None
    except Exception as exc:
        logger.warning("Prompt audit failed: %s", exc)
        return None


def write_final_article(
    *,
    master_prompt: str,
    revision_notes: list[str] | None = None,
) -> str:
    feedback_block = ""
    if revision_notes:
        feedback_block = (
            "\n[AUDITOR FEEDBACK]\nThe previous draft failed the quality audit. Solve every problem below by rewriting the full article, "
            "then return only the improved finished article. Do not mention these notes.\n"
            + "\n".join(f"- {note}" for note in revision_notes)
        )

    prompt = f"""
{master_prompt}
{feedback_block}
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


async def generate_gold_hunter_seeds(url: str, url_content: str) -> dict[str, Any] | None:
    """Generate 3 high-value seed keywords using the Gold Nugget Agent prompt."""
    if not is_ai_configured():
        logger.error("AI API key not configured")
        return None

    prompt = f"""
[SYSTEM COMMANDS]

You are the Gold Nugget Agent. Your purpose is to mine 3 high-value seed keywords from any given URL.

INPUT URL: {url}
URL CONTENT:
{url_content[:10000]}

PHASE 1: SITE AUDIT
Audit the URL's visible content (Title, H1, Meta, Features, Copy). Extract:
- Primary Keyword
- Industry / Niche
- Core Action (the exact transformation the tool performs)
- Target Audience
- Capabilities (DOES)
- Hard Boundaries (DOES NOT)

PHASE 2: DOMAIN FENCING
Ban umbrella terms (general, basic, professional, engineering). Block adjacent misaligned domains (e.g., IT for an electronics site). If the Primary Keyword is vague, force-inject the strongest specific anchor discovered during the audit to kill ambiguity.

PHASE 3: GAP DISCOVERY
Identify missing elements. Classify into:
- Tool Gaps (missing features, sub-tools, variations)
- Content Gaps (missing educational guides, comparisons, use-case tutorials)
Generate a pool of 5-6 candidate seeds that directly relate to the Core Action.

PHASE 4: THE TRIPLE GATE FILTER (MANDATORY)
Reject any seed that fails any single gate.

Gate A (Volume): Must imply 1,000+ monthly searches. Reject unnatural, forum-style, or zero-volume phrases.
Gate B (Sitemap Depth): The Top 10 results must be content-heavy sites with deep sitemaps (Wikipedia, Verywell Mind, Edutopia, TechCrunch, DataCamp, established educational or media domains). Reject seeds whose Top 10 are shallow personal blogs, app stores, Quora, or single-page tools.
Gate C (Thematic Relevance): The seed must explicitly tie back to the site's Core Action. If the tool spins a wheel, the seed must contain "wheel", "spin", "random picker", or a direct use-case of that mechanic. Reject pure psychology, fitness, or engineering drifts that do not anchor to the tool's specific mechanic.

PHASE 5: USE-CASE BROADENING (THE PIVOT)
If the Primary Keyword is a short head-term (e.g., "yes or no wheel", "dot plot maker") that fails the Sitemap Gate due to shallow tool competitors, do NOT output the head-term. Do NOT drift into adjacent fields. Instead, force-inject a high-volume, content-rich use-case modifier (e.g., "for classroom", "best [category] websites", "how to make [tool] for [purpose]") to pivot the search toward educational, review, or tutorial sites while keeping the mechanic intact.

PHASE 6: FINAL OUTPUT
Select the 3 strongest seeds that pass all three gates. Provide your full audit summary and the final 3 seeds, each with a one-sentence justification covering why it passed the Volume Gate, Sitemap Gate, and Relevance Gate.

Return ONLY a JSON object in this exact format:
{{
  "audit_summary": "Your detailed audit summary from Phase 1-5.",
  "seeds": [
    {{
      "keyword": "seed phrase 1",
      "justification": "Why it passed..."
    }},
    {{
      "keyword": "seed phrase 2",
      "justification": "Why it passed..."
    }},
    {{
      "keyword": "seed phrase 3",
      "justification": "Why it passed..."
    }}
  ]
}}
"""
    try:
        payload = await _achat_json(
            system_prompt="You output only valid JSON. You are the Gold Nugget Agent.",
            user_prompt=prompt,
            temperature=0.3,
            max_tokens=2500,
        )
        return payload if isinstance(payload, dict) else None
    except Exception as exc:
        logger.warning("Gold hunter failed: %s", exc)
        return None


def _validate_hub_and_spoke(payload: dict, total_kws: int) -> str | None:
    if not payload or "hubs" not in payload:
        return "Missing 'hubs' array."
    for hub in payload.get("hubs", []):
        if hub.get("hub_title", "").startswith("🗑️"):
            continue
        for silo in hub.get("sub_silos", []):
            layers = silo.get("layers", {})
            total_articles = sum(len(spokes) for spokes in layers.values())
            if total_kws > 40 and total_articles < 8:
                return f"Sub-Silo '{silo.get('hub_title')}' has only {total_articles} articles. You MUST merge it into a neighboring sub-silo to meet the 8-article minimum."
            layer_names = " ".join(layers.keys()).lower()
            if "foundation" not in layer_names and "action" not in layer_names:
                return f"Sub-Silo '{silo.get('hub_title')}' is missing required structural layers (Foundations or Action)."
    return None


async def cluster_hub_and_spoke(keywords: list[dict[str, Any]], main_keyword: str = "your core topic") -> dict[str, Any] | None:
    """Cluster keywords into categorized Hub and Spoke architectures, strictly avoiding cannibalization."""
    if not is_ai_configured() or not keywords:
        return None

    trimmed = keywords[:500]
    prompt = f"""
Take a raw, flat Hub-and-Spoke list of keywords and transform it into a visually optimized, layered, ranking-ready SEO architecture.
You are a Senior SEO Content Strategist and Topical Authority Architect.

[TASK - STEP-BY-STEP STRICT ENFORCEMENT]
You must process the provided keywords sequentially following these steps to build the Topical Map:

STEP 1: DYNAMIC TOPIC EXTRACTION & MASTER HUB
Your Master Hub MUST be built around this core seed topic: "{main_keyword}".
This is your "Primary Core Entity".
Assign it as "📍 MASTER HUB: [Broadest Search Intent related to {main_keyword}]". 
Output its explicit target keyword in the `target_keyword` field.
HARD RULE: You MUST create exactly ONE (1) Master Hub based strictly on the core seed topic. Do NOT create multiple Master Hubs.

STEP 2: HUB SLUG INTEGRITY & UNIQUENESS
- The Master Hub's target keyword MUST perfectly match the Primary Core Entity tokens.
- NO Sub-Silo is allowed to use that exact same target keyword.
- If a Sub-Silo wants to use the Master Hub target keyword, you MUST append a unique suffix like `hub` or `overview`.

STEP 3: TOPICAL NEIGHBORHOOD FIREWALL
Identify distinct sub-themes for the Master Hub to create Sub-Silos.
- Limit to 3 to 5 Sub-Silos maximum. Rank by topical density, keep the top 5 only.
- Each sub-silo must have at least 8 supporting articles. Merge sub-silos with fewer into the closest neighbor.

STEP 4: COMMERCIAL CONSOLIDATION
- If you are generating Commercial/Money pages, you are only allowed to create ONE primary commercial URL per distinct product category.
- DO NOT generate separate URLs for micro-audiences (e.g., "best apps for professionals", "best apps for students").
- Instead, create ONE master commercial page and append the micro-audiences as H2 anchor links using `[Include H2: ...]`. Delete the extra spokes.

STEP 5: BEGINNER PAGE LIMIT
- If you are generating Action or Foundation pages for beginners, limit to a maximum of TWO (2) beginner pages per silo:
  - Page 1 (The Theory): "[Topic] Basics"
  - Page 2 (The Action): "How to use [Topic] / Tutorial"
- Consolidate any extras into H2 subheadings on these two pages using `[Include H2: ...]`.

STEP 6: INTENT TAGS & ENTITIES
- If a keyword is a tool/calculator/software, output it with a [Tool] tag in the title.
- ANTI-CANNIBALIZATION: If multiple variations share the exact same search intent (>0.65 similarity), keep the highest volume one as the target keyword and append the rest as `[Include H2: keyword]`.
- ENTITIES: If "type" == "entity", YOU ARE STRICTLY FORBIDDEN from creating a standalone article. Append the as `[Include H2: entity]` to the most relevant article.

[OUTPUT SCHEMA - STRICT JSON ONLY]
{{
  "_planning_thought": "Before generating URLs, explain your logic. E.g., 'I will create 3 sub-silos. Sub-Silo 1 has 12 articles. Sub-Silo 2 has 9 articles. I am verifying no sub-silos have fewer than 8 articles.'",
  "_deduplication_check": {{
    "layer_1_swapped_words": "Checked: Did any URLs swap words? If yes, I deleted the weaker one.",
    "layer_2_synonyms": "Checked: Did any URLs use synonyms like 'understanding' vs 'meanings', 'test' vs 'quiz', 'guide' vs 'tutorial'? If yes, I merged them.",
    "layer_3_overlap_70_percent": "Checked: Do any URLs share more than 70% of the same words (e.g., 'how-to-draw' vs 'step-by-step-draw')? If yes, I deleted the weaker one."
  }},
  "hubs": [
    {{
      "hub_title": "📍 MASTER HUB: [Broadest Search Intent / Topic]",
      "target_keyword": "[exact keyword]",
      "layers": {{
        "🧱 FOUNDATION SPOKES (Authority)": ["What Is [Core Entity]? Complete Guide (Target Keyword: what is [core entity])"],
        "⚙️ CORE STRATEGY": ["How to Implement [Core Entity] (Target Keyword: how to implement [core entity])"]
      }},
      "sub_silos": [
        {{
          "hub_title": "🪐 SUB-SILO 1: LEARNING HUB — How to Use [Core Entity]",
          "target_keyword": "[exact keyword]",
          "layers": {{
            "🧱 Foundations": ["How to Use [Core Entity] (Target Keyword: how to use [core entity])"],
            "⚙️ Action": ["Best Practices for [Core Entity] [Tool] (Target Keyword: best practices for [core entity]) [Include H2: entity_from_list]"],
            "💰 Money": [],
            "⚡️ ZERO COMPETITION QUICK-WINS": ["Easy [Core Entity] Writing (Target Keyword: easy [core entity] writing)"]
          }}
        }}
      ]
    }},
    {{
      "hub_title": "🗑️ NOISE / DISCARD",
      "target_keyword": "noise",
      "layers": {{
        "Unrelated Keywords": ["(Target Keyword: [unrelated keyword])"]
      }},
      "sub_silos": []
    }}
  ]
}}

[EXPLICIT FAILURE CONDITIONS]
If you violate any of the following, your response will be programmatically REJECTED and you will be penalized:
1. Creating a Sub-Silo with fewer than 8 total articles. (MERGE THEM!)
2. Missing required layers within a Sub-Silo.

Target Keywords List:
{json.dumps(trimmed)}

Main Keywords (Create Master Hubs and Spokes using ONLY these):
{json.dumps([kw for kw in trimmed if kw.get("type") != "entity"])}

Entity Keywords (DO NOT CREATE SPOKES FOR THESE. Distribute and append them as [Include H2: entity] to the most relevant Spokes created above):
{json.dumps([kw["phrase"] for kw in trimmed if kw.get("type") == "entity"])}
"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            payload = await _achat_json(
                system_prompt="You are a Senior SEO Content Strategist. You output only valid JSON objects matching the SEO architecture schema.",
                user_prompt=prompt,
                temperature=0.15 + (attempt * 0.1),
                max_tokens=8000,
            )
            if isinstance(payload, dict):
                err = _validate_hub_and_spoke(payload, len(trimmed))
                if err and attempt < max_retries - 1:
                    logger.warning(f"Validation failed on attempt {attempt+1}: {err}. Retrying...")
                    prompt += f"\n\n[SYSTEM FEEDBACK - ATTEMPT {attempt+1} FAILED]\nYour previous output was REJECTED because: {err}\nYou MUST fix this immediately."
                    continue
                return payload
            return None
        except Exception as exc:
            logger.error("Failed to cluster hub and spoke via %s on attempt %d: %s", ai_provider_name(), attempt+1, exc)
            if attempt == max_retries - 1:
                return None
