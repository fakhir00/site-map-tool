import json
import logging
import re
from typing import Any

from openai import AsyncOpenAI, OpenAI

from app.config import settings

logger = logging.getLogger(__name__)

ALLOWED_KEYWORD_TYPES = {"primary", "lsi", "long-tail", "entity", "heading"}


def _keyword_generation_support_is_valid(
    item: dict[str, Any],
    seed_keywords: list[str],
    evidence_phrases: list[str] | None,
    audit_summary: str | None,
) -> bool:
    """Require explicit evidence, with safe support for legacy model output."""
    from nlp.keywords import clean_phrase, normalize_seed_keywords

    source = str(item.get("support_source") or "").strip().lower()
    support = clean_phrase(str(item.get("support_phrase") or ""))
    if not support:
        # Some providers occasionally return the previous two-field schema.
        # Accept that response only when the complete seed phrase appears in
        # the keyword. This retains useful direct long-tails without allowing
        # broad semantic guesses to bypass provenance checks.
        if source:
            return False
        phrase = clean_phrase(str(item.get("phrase") or ""))
        return any(
            re.search(rf"\b{re.escape(seed)}\b", phrase)
            for seed in normalize_seed_keywords(seed_keywords)
        )
    if source == "seed":
        return support in set(normalize_seed_keywords(seed_keywords))
    if source == "competitor":
        evidence = {clean_phrase(value) for value in (evidence_phrases or []) if value}
        return support in evidence
    if source == "audit":
        audit = clean_phrase(audit_summary or "")
        return bool(audit and len(support.split()) >= 2 and support in audit)
    return False


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
        timeout=settings.AI_REQUEST_TIMEOUT,
        max_retries=0,
    )


def _async_client(use_writing_model: bool = False) -> AsyncOpenAI:
    _provider, base_url, api_key, _model = _provider_config(use_writing_model)
    return AsyncOpenAI(
        base_url=base_url,
        api_key=api_key,
        timeout=settings.AI_REQUEST_TIMEOUT,
        max_retries=0,
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
    import json
    
    if not is_ai_configured() or not target_keywords:
        return {
            "anchor_terms": [], "scope_terms": [], "core_terms": [],
            "generic_terms": [], "negative_terms": [],
        }

    cache_key = json.dumps([target_keywords, audit_summary])
    if cache_key in _semantic_cache:
        return _semantic_cache[cache_key]

    prompt = f"""
You are an expert SEO taxonomist and NLP analyzer. 
I have a website defined by these Seed Keywords: {json.dumps(target_keywords)}
And this Context/Audit Summary:
{audit_summary or "No summary provided. Rely solely on seed keywords."}

Your task is to analyze the semantic core of this website and break it down into three distinct JSON arrays to be used as a Python stopword/gate filter.

1. "anchor_terms": Exact names, synonyms, or very close first-hop names for the PRIMARY entity in the first seed/EMD. These must keep the same topical niche, not merely be words mentioned for comparison. Example: lunar -> moon is valid; solar is not. Circuit -> electrical or electronic can be valid. Limit to 8 terms.
2. "scope_terms": Functions or subject qualifiers that must accompany an anchor to describe this exact site. Example for lunar age calculator: age, calendar, birth, date, conversion, calculate. Example for circuit diagram maker: diagram, schematic, wiring, electronics, design. Limit to 30 terms.
3. "core_terms": Other close entities that are useful for ranking but are not sufficient relevance proof by themselves. Limit to 30 terms.
4. "generic_terms": Generic modifiers that DO NOT define the niche (for example tool, app, system, calculator). Limit to 30 terms.
5. "negative_terms": Terms from common alternate meanings of the primary words and unrelated niches. For lunar age, include astronomy drift such as planet, mars, eclipse, orbit, astronomy, and space while retaining legitimate lunar-calendar comparisons. Never put an anchor synonym itself (such as moon) in negative_terms. Limit to 30 terms.

Ensure all terms are lowercase strings.
Do not output anything except valid JSON matching this schema:
{{
  "anchor_terms": ["..."],
  "scope_terms": ["..."],
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
                "anchor_terms": _extract_words(payload.get("anchor_terms", [])),
                "scope_terms": _extract_words(payload.get("scope_terms", [])),
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
        
    return {"anchor_terms": [], "scope_terms": [], "core_terms": [], "generic_terms": [], "negative_terms": []}


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


async def generate_ai_keywords(
    seed_keywords: list[str],
    topic_terms: set[str] | None = None,
    negative_terms: set[str] | None = None,
    audit_summary: str | None = None,
    apply_gap_filter: bool = True,
    target_count: int = 25,
    exclude_phrases: set[str] | None = None,
    evidence_phrases: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Generate SEO keyword recommendations using the configured AI provider."""
    if not is_ai_configured():
        logger.error("AI API key not configured")
        return []

    from nlp.keywords import clean_phrase, is_publishable_keyword, is_topic_relevant_keyword, seed_keyword_terms

    if topic_terms is None:
        topic_terms = seed_keyword_terms(seed_keywords)
    target_count = max(5, min(int(target_count), 60))
    excluded = sorted(exclude_phrases or set())[-400:]
    evidence = list(dict.fromkeys(evidence_phrases or []))[:300]
    prompt = f"""
You are an expert SEO keyword strategist. Use the seed keywords as the strict topic boundary.
Generate up to {target_count} high-quality, distinct keyword opportunities. Return fewer when the supplied evidence and context do not support that many. Distribute valid results across primary, LSI, long-tail, entity, and heading types, with most as useful page-level primary or long-tail searches.

Seed keywords:
{json.dumps(seed_keywords)}

Website context:
{audit_summary or "No additional context supplied."}

Already collected phrases (do not repeat or paraphrase with the same search intent):
{json.dumps(excluded)}

Phrases observed on the selected competitor pages (use these as evidence and topical vocabulary):
{json.dumps(evidence)}

Quality rules:
- Allocate the output evenly across every seed keyword; no seed may be ignored.
- Use the website context to match its competition, target audience, core action, capabilities, boundaries, and search intent.
- Prefer genuine content gaps supported by the competitor evidence. You may form a useful long-tail from an observed concept, but do not invent a disconnected topic.
- Each result must cite exactly one supplied seed, one exact competitor phrase, or a short exact phrase from the website context as its support. Never claim support that is absent from the inputs.
- A phrase must represent a query a real member of the target audience would search. Do not create variants merely to reach the requested count.
- Do not attach generic modifiers such as pricing, security, training, trends, templates, or software unless that exact need is supported by the competitor evidence or website context.
- Every keyword MUST be highly semantically relevant to the primary seed keywords.
- Absolutely NO unrelated keywords, hallucinated terms, or irrelevant BS.
- If a keyword does not directly relate to the user intent of the seed keyword, discard it.
- Reject bogus, random, generic, broad, off-topic, or awkward phrases.
- Do not invent fake brands, fake products, fake people, or fake entities.
- Keep phrases natural, lowercase, 2 to 6 words, and suitable for an SEO keyword table.
- Every phrase must include at least one meaningful seed keyword term exactly, so the app can safely reject unrelated junk.
- When competitor or audit support is unavailable, preserve one complete seed phrase unchanged inside the keyword and use that seed as the support.
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
- "support_source": one of "seed", "competitor", or "audit"
- "support_phrase": the exact seed, exact competitor phrase, or short exact phrase from the website context that supports this keyword
"""
    try:
        payload = await _achat_json(
            system_prompt="You output only valid JSON arrays.",
            user_prompt=prompt,
            temperature=0.35,
            max_tokens=max(2200, target_count * 85),
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
                if not is_publishable_keyword(phrase, min_words=2, negative_terms=negative_terms):
                    continue
                if not is_topic_relevant_keyword(phrase, seed_keywords, topic_terms, negative_terms):
                    continue
                if not _keyword_generation_support_is_valid(kw, seed_keywords, evidence, audit_summary):
                    continue
                valid_keywords.append({
                    "phrase": phrase,
                    "type": kw_type,
                })
                seen_phrases.add(phrase)
        
        if valid_keywords:
            if not apply_gap_filter:
                return valid_keywords

            import asyncio
            filtered = await asyncio.to_thread(
                filter_keyword_gap_recommendations,
                seed_keywords,
                valid_keywords,
                audit_summary=audit_summary,
                max_keywords=target_count,
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


def generate_ai_keywords_sync(
    seed_keywords: list[str],
    topic_terms: set[str] | None = None,
    negative_terms: set[str] | None = None,
    audit_summary: str | None = None,
    apply_gap_filter: bool = True,
    target_count: int = 25,
    exclude_phrases: set[str] | None = None,
    evidence_phrases: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Synchronous version of generate_ai_keywords for background worker pipelines."""
    if not is_ai_configured():
        logger.error("AI API key not configured")
        return []

    from nlp.keywords import clean_phrase, is_publishable_keyword, is_topic_relevant_keyword, seed_keyword_terms

    if topic_terms is None:
        topic_terms = seed_keyword_terms(seed_keywords)
    target_count = max(5, min(int(target_count), 60))
    excluded = sorted(exclude_phrases or set())[-400:]
    evidence = list(dict.fromkeys(evidence_phrases or []))[:300]
    prompt = f"""
You are an expert SEO keyword strategist. Use the seed keywords as the strict topic boundary.
Generate up to {target_count} high-quality, distinct keyword opportunities. Return fewer when the supplied evidence and context do not support that many. Distribute valid results across primary, LSI, long-tail, entity, and heading types, with most as useful page-level primary or long-tail searches.

Seed keywords:
{json.dumps(seed_keywords)}

Website context:
{audit_summary or "No additional context supplied."}

Already collected phrases (do not repeat or paraphrase with the same search intent):
{json.dumps(excluded)}

Phrases observed on the selected competitor pages (use these as evidence and topical vocabulary):
{json.dumps(evidence)}

Quality rules:
- Allocate the output evenly across every seed keyword; no seed may be ignored.
- Use the website context to match its competition, target audience, core action, capabilities, boundaries, and search intent.
- Prefer genuine content gaps supported by the competitor evidence. You may form a useful long-tail from an observed concept, but do not invent a disconnected topic.
- Each result must cite exactly one supplied seed, one exact competitor phrase, or a short exact phrase from the website context as its support. Never claim support that is absent from the inputs.
- A phrase must represent a query a real member of the target audience would search. Do not create variants merely to reach the requested count.
- Do not attach generic modifiers such as pricing, security, training, trends, templates, or software unless that exact need is supported by the competitor evidence or website context.
- Every keyword MUST be highly semantically relevant to the primary seed keywords.
- Absolutely NO unrelated keywords, hallucinated terms, or irrelevant BS.
- If a keyword does not directly relate to the user intent of the seed keyword, discard it.
- Reject bogus, random, generic, broad, off-topic, or awkward phrases.
- Do not invent fake brands, fake products, fake people, or fake entities.
- Keep phrases natural, lowercase, 2 to 6 words, and suitable for an SEO keyword table.
- Every phrase must include at least one meaningful seed keyword term exactly, so the app can safely reject unrelated junk.
- When competitor or audit support is unavailable, preserve one complete seed phrase unchanged inside the keyword and use that seed as the support.
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
- "support_source": one of "seed", "competitor", or "audit"
- "support_phrase": the exact seed, exact competitor phrase, or short exact phrase from the website context that supports this keyword
"""
    try:
        payload = _chat_json(
            system_prompt="You output only valid JSON arrays.",
            user_prompt=prompt,
            temperature=0.35,
            max_tokens=max(2200, target_count * 85),
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
                if not is_publishable_keyword(phrase, min_words=2, negative_terms=negative_terms):
                    continue
                if not is_topic_relevant_keyword(phrase, seed_keywords, topic_terms, negative_terms):
                    continue
                if not _keyword_generation_support_is_valid(kw, seed_keywords, evidence, audit_summary):
                    continue
                valid_keywords.append({
                    "phrase": phrase,
                    "type": kw_type,
                })
                seen_phrases.add(phrase)
        
        if valid_keywords:
            if not apply_gap_filter:
                return valid_keywords

            filtered = filter_keyword_gap_recommendations(
                seed_keywords,
                valid_keywords,
                audit_summary=audit_summary,
                max_keywords=target_count,
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
    """Extracts SEO keywords from scraped full text using RAKE and KeyBERT (Option B)."""
    if not urls:
        return []

    from nlp.keywords import clean_phrase, is_publishable_keyword, is_topic_relevant_keyword, seed_keyword_terms, extract_keywords_from_page
    
    if not topic_terms:
        topic_terms = seed_keyword_terms(seed_keywords)
    
    results_by_phrase: dict[str, dict[str, Any]] = {}
    type_priority = {"entity": 1, "heading": 2, "lsi": 3, "primary": 4}
    
    for u in urls:
        if not getattr(u, "scraped_text", None):
            continue
            
        try:
            kw_result = extract_keywords_from_page(
                u.scraped_text,
                h1=u.h1,
                use_keybert=settings.ENABLE_KEYBERT,
                use_spacy=settings.ENABLE_SPACY,
            )
            
            candidates = []
            # Primary keywords (RAKE)
            for phrase, score in kw_result.primary:
                candidates.append((phrase, "primary"))
            # LSI keywords (KeyBERT)
            for phrase, score in kw_result.lsi:
                candidates.append((phrase, "lsi"))
            # Entities
            for phrase, label in kw_result.entities:
                candidates.append((phrase, "entity"))
            # Heading terms
            for phrase in kw_result.heading_keywords:
                candidates.append((phrase, "heading"))
                
            for phrase, kw_type in candidates:
                if (
                    is_publishable_keyword(phrase, min_words=2, negative_terms=negative_terms)
                    and is_topic_relevant_keyword(phrase, seed_keywords, topic_terms, negative_terms)
                ):
                    phrase = clean_phrase(phrase)
                    entry = results_by_phrase.setdefault(
                        phrase,
                        {
                            "source_phrase": phrase,
                            "phrase": phrase,
                            "type": kw_type,
                            "volume": "Medium",
                            "url_ids": [],
                            "frequency": 0,
                        },
                    )
                    if type_priority.get(kw_type, 0) > type_priority.get(entry.get("type", ""), 0):
                        entry["type"] = kw_type
                    url_id = str(u.id)
                    if url_id not in entry["url_ids"]:
                        entry["url_ids"].append(url_id)
                    entry["frequency"] += 1
        except Exception as exc:
            logger.error("Error extracting keywords from page: %s", exc)

    results = list(results_by_phrase.values())
    results.sort(
        key=lambda item: (
            len(item.get("url_ids", [])),
            int(item.get("frequency") or 0),
            len(str(item.get("phrase") or "").split()),
        ),
        reverse=True,
    )
    return results


async def generate_ai_top_picks(
    seed_keywords: list[str],
    existing_keywords: list[str],
    topic_terms: set[str] | None = None,
    negative_terms: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Generate top pick recommendations from existing keywords."""
    if not is_ai_configured():
        return []

    from nlp.keywords import clean_phrase, is_publishable_keyword, seed_keyword_terms

    if topic_terms is None:
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
                if not is_publishable_keyword(phrase, min_words=2, topic_terms=topic_terms, negative_terms=negative_terms):
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

    trimmed_candidates = _balanced_keyword_candidates(
        seed_keywords,
        candidates,
        settings.AI_KEYWORD_GAP_CANDIDATE_LIMIT,
    )
    
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

**Step 2: KEYWORD-LEVEL DEDUPLICATION**
- Remove exact duplicates and word-order-only duplicates.
- Keep useful related nuances, audience modifiers, questions, comparisons, problems, and use cases. These are valuable supporting keywords even when they later belong on the same page.
- Do not collapse a whole topic family into one phrase. URL cannibalization is handled later by the Hub-and-Spoke builder, where related nuances become H2 sections.

**Step 3: Evidence and usefulness gate**
- Keep queries supported by the supplied competitor evidence and useful for a distinct search intent.
- Do not invent search-volume numbers or discard a relevant query based on guessed volume.

**Step 4: Final Output**
- Return ALL deduplicated keywords that passed Steps 1-3 (maximum {max_keywords} total).
- Return ONLY a JSON array of objects. Do not include markdown formatting or explanations.
- Each returned object must include:
  - "source_phrase": exact original phrase from the candidates
  - "phrase": the normalized search query
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

        from nlp.keywords import clean_phrase, is_publishable_keyword

        valid: list[dict[str, Any]] = []
        source_candidates = {
            clean_phrase(str(candidate.get("phrase", ""))): candidate
            for candidate in trimmed_candidates
            if candidate.get("phrase")
        }
        candidate_phrases = set(source_candidates)
        for item in payload:
            if not isinstance(item, dict):
                continue
            source_phrase = clean_phrase(str(item.get("source_phrase") or item.get("source") or ""))
            phrase = clean_phrase(str(item.get("phrase") or ""))
            keyword_type = normalize_keyword_type(item.get("type"))
            volume = str(item.get("volume") or "")
            if not source_phrase and phrase in candidate_phrases:
                source_phrase = phrase
            if not source_phrase or source_phrase not in candidate_phrases or not phrase:
                continue
            if not is_publishable_keyword(phrase, min_words=2):
                continue
            source_candidate = source_candidates[source_phrase]
            valid_item = {
                "source_phrase": source_phrase,
                "phrase": phrase,
                "type": keyword_type,
                "volume": volume,
            }
            for field in ("url_ids", "frequency", "competitor_domain_count", "competitor_domains", "score"):
                if field in source_candidate:
                    valid_item[field] = source_candidate[field]
            valid.append(valid_item)
            if len(valid) >= max_keywords:
                break

        return valid
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse JSON from %s gap filter: %s", ai_provider_name(), exc)
        return None
    except Exception as exc:
        logger.error("Failed to filter keyword gaps via %s: %s", ai_provider_name(), exc)
        return None


def _balanced_keyword_candidates(
    seed_keywords: list[str],
    candidates: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    """Round-robin candidate phrases across seed anchors before the AI filter."""
    from nlp.keywords import keyword_terms, seed_keyword_terms

    buckets: list[list[dict[str, Any]]] = []
    for seed in seed_keywords:
        anchors = seed_keyword_terms([seed])
        buckets.append([
            item for item in candidates
            if keyword_terms(str(item.get("phrase") or ""), min_len=2) & anchors
        ])

    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    index = 0
    while len(result) < limit and any(index < len(bucket) for bucket in buckets):
        for bucket in buckets:
            if index >= len(bucket):
                continue
            item = bucket[index]
            key = str(item.get("phrase") or "").strip().lower()
            if key and key not in seen:
                result.append(item)
                seen.add(key)
                if len(result) >= limit:
                    return result
        index += 1

    for item in candidates:
        key = str(item.get("phrase") or "").strip().lower()
        if key and key not in seen:
            result.append(item)
            seen.add(key)
            if len(result) >= limit:
                break
    return result


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
Maintain coverage across every seed keyword: when relevant candidates exist for a seed, accept at least two for that seed before adding extra domains for another seed. The candidate `queries` field shows which seed/search discovered it.
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
            return None

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
        return None


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
    """Generate 3-5 high-value seed keywords using the Gold Nugget Agent prompt."""
    if not is_ai_configured():
        logger.error("AI API key not configured")
        return None

    prompt = f"""
[SYSTEM COMMANDS]

You are the Gold Nugget Agent. Your purpose is to mine 3 to 5 high-value seed keywords from any given URL.

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
Generate a pool of 8-10 candidate seeds that directly relate to the Core Action.

PHASE 4: THE TRIPLE GATE FILTER (MANDATORY)
Reject any seed that fails any single gate.

Gate A (Volume): Must imply 1,000+ monthly searches. Reject unnatural, forum-style, or zero-volume phrases.
Gate B (Sitemap Depth): The Top 10 results must be content-heavy sites with deep sitemaps (Wikipedia, Verywell Mind, Edutopia, TechCrunch, DataCamp, established educational or media domains). Reject seeds whose Top 10 are shallow personal blogs, app stores, Quora, or single-page tools.
Gate C (Thematic Relevance): The seed must explicitly tie back to the site's Core Action. If the tool spins a wheel, the seed must contain "wheel", "spin", "random picker", or a direct use-case of that mechanic. Reject pure psychology, fitness, or engineering drifts that do not anchor to the tool's specific mechanic.

PHASE 5: USE-CASE BROADENING (THE PIVOT)
If the Primary Keyword is a short head-term (e.g., "yes or no wheel", "dot plot maker") that fails the Sitemap Gate due to shallow tool competitors, do NOT output the head-term. Do NOT drift into adjacent fields. Instead, force-inject a high-volume, content-rich use-case modifier (e.g., "for classroom", "best [category] websites", "how to make [tool] for [purpose]") to pivot the search toward educational, review, or tutorial sites while keeping the mechanic intact.

PHASE 6: FINAL OUTPUT
Select 3 to 5 distinct seeds that pass all three gates. Never return fewer than 3 or more than 5. Provide your full audit summary and each final seed with a one-sentence justification covering why it passed the Volume Gate, Sitemap Gate, and Relevance Gate.

Return ONLY a JSON object in this exact format:
{{
  "audit_summary": {{
    "primary_keyword": "exact primary topic",
    "industry_niche": "specific niche",
    "core_action": "what the site helps users accomplish",
    "target_audience": ["specific audience segments"],
    "search_intents": ["informational, commercial, transactional, or tool-use intents that apply"],
    "capabilities": ["what the product/site does"],
    "hard_boundaries": ["adjacent topics it does not serve"],
    "competitor_profile": "the kinds of domains that are true search competitors",
    "content_opportunities": ["evidence-based topic families to investigate"]
  }},
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


def _hub_intent_tokens(phrase: str) -> set[str]:
    """Normalize words used to detect duplicate URLs and search intent."""
    from nlp.keywords import STOPWORDS, clean_phrase

    synonyms = {
        "builder": "tool", "builders": "tool", "creator": "tool",
        "creators": "tool", "generator": "tool", "generators": "tool",
        "maker": "tool", "makers": "tool", "software": "tool", "tools": "tool",
        "app": "tool", "apps": "tool", "visualizer": "tool",
        "drawing": "diagram", "drawings": "diagram", "schematic": "diagram",
        "schematics": "diagram", "tutorial": "guide", "tutorials": "guide",
        "meanings": "meaning", "companies": "agency", "services": "agency",
        "electrical": "electric", "electronic": "electric", "electronics": "electric",
    }
    weak_qualifiers = {
        "basic", "complete", "electric", "find", "free", "online", "out",
        "overview", "simple", "tool",
    }
    tokens: set[str] = set()
    for token in clean_phrase(phrase).replace("-", " ").split():
        if token in STOPWORDS:
            continue
        if token.endswith("s") and not token.endswith("ss") and len(token) > 4:
            token = token[:-1]
        token = synonyms.get(token, token)
        if token not in weak_qualifiers:
            tokens.add(token)
    return tokens


def _hub_intent_similarity(left: str, right: str) -> float:
    left_tokens = _hub_intent_tokens(left)
    right_tokens = _hub_intent_tokens(right)
    union = left_tokens | right_tokens
    if not union:
        return 0.0
    intersection = len(left_tokens & right_tokens)
    jaccard = intersection / len(union)
    shorter = min(len(left_tokens), len(right_tokens))
    containment = intersection / shorter if shorter else 0.0
    return max(jaccard, containment)


def _hub_same_page_intent(left: str, right: str) -> bool:
    """Return true when two targets should resolve to one canonical URL."""
    left_tokens = _hub_intent_tokens(left)
    right_tokens = _hub_intent_tokens(right)
    if not left_tokens or not right_tokens:
        return False
    if left_tokens == right_tokens:
        return True
    union = left_tokens | right_tokens
    jaccard = len(left_tokens & right_tokens) / len(union)
    if jaccard >= 0.82:
        return True

    def mode(value: str) -> str:
        words = set(value.lower().replace("-", " ").split())
        if words & {"symbol", "symbols", "abbreviation", "abbreviations"}:
            return "symbols"
        if words & {"example", "examples", "idea", "ideas"}:
            return "examples"
        if words & {"tutorial", "tutorials", "guide", "guides"} or "how" in words:
            return "tutorial"
        if words & {"definition", "definitions", "meaning", "meanings", "define"}:
            return "definition"
        if words & {"best", "comparison", "compare", "review", "reviews", "versus", "vs"}:
            return "comparison"
        if words & {
            "app", "apps", "builder", "creator", "generator", "maker",
            "software", "tool", "tools", "visualizer",
        }:
            return "tool"
        return "topic"

    left_mode, right_mode = mode(left), mode(right)
    if left_mode != right_mode:
        return False
    protected_subtopics = {
        "analog", "digital", "parallel", "series", "short", "logic", "nand",
        "xor", "counter", "encoder", "decoder", "adder", "multiplexer",
    }
    if (left_tokens & protected_subtopics) != (right_tokens & protected_subtopics):
        return False
    if left_mode == "symbols" and "symbol" in left_tokens & right_tokens:
        return True
    shorter = min(len(left_tokens), len(right_tokens))
    containment = len(left_tokens & right_tokens) / shorter if shorter else 0.0
    return left_mode != "topic" and containment >= 0.75


def _hub_slug(phrase: str) -> str:
    from nlp.keywords import clean_phrase
    return re.sub(r"[^a-z0-9]+", "-", clean_phrase(phrase)).strip("-")


def _hub_page_family(phrase: str) -> str | None:
    """Return the broader page intent for modifier variants such as `X for Y`."""
    from nlp.keywords import clean_phrase

    words = clean_phrase(phrase).split()
    for index, word in enumerate(words):
        if word in {"for", "with", "in", "on", "by", "using"} and index >= 2 and index < len(words) - 1:
            return " ".join(words[:index])
    return None


def _prepare_hub_page_keywords(
    keywords: list[dict[str, Any]],
    main_keyword: str,
) -> list[dict[str, Any]]:
    """Collapse keywords that belong on one URL before architecture generation."""
    from nlp.keywords import clean_phrase

    normalized: list[dict[str, Any]] = []
    by_phrase: dict[str, dict[str, Any]] = {}
    for item in keywords:
        phrase = clean_phrase(str(item.get("phrase") or ""))
        if not phrase:
            continue
        if phrase in by_phrase:
            existing_h2s = by_phrase[phrase].setdefault("h_tags", [])
            existing_h2s.extend(str(value) for value in (item.get("h_tags") or []) if value)
            continue
        copied = {**item, "phrase": phrase}
        copied["h_tags"] = list(dict.fromkeys(
            clean_phrase(str(value)) for value in (item.get("h_tags") or []) if clean_phrase(str(value))
        ))
        normalized.append(copied)
        by_phrase[phrase] = copied

    families: dict[str, list[dict[str, Any]]] = {}
    for item in normalized:
        family = _hub_page_family(item["phrase"])
        if family:
            families.setdefault(family, []).append(item)

    consumed: set[str] = set()
    prepared: list[dict[str, Any]] = []
    main = clean_phrase(main_keyword)
    for item in normalized:
        phrase = item["phrase"]
        if phrase in consumed:
            continue
        family = phrase if phrase in families and len(families[phrase]) >= 2 else _hub_page_family(phrase)
        members = families.get(family or "", [])
        if family and len(members) >= 2:
            existing_parent = by_phrase.get(family)
            parent = dict(existing_parent or item)
            parent["phrase"] = family
            parent["type"] = "primary" if parent.get("type") == "entity" else parent.get("type", "long-tail")
            h2s = list(parent.get("h_tags") or [])
            for member in members:
                consumed.add(member["phrase"])
                if member["phrase"] != family:
                    h2s.append(member["phrase"])
                h2s.extend(member.get("h_tags") or [])
            parent["h_tags"] = list(dict.fromkeys(value for value in h2s if value and value != family))
            if family == main:
                parent["phrase"] = main
            prepared.append(parent)
            if existing_parent:
                consumed.add(family)
            continue
        prepared.append(item)
        consumed.add(phrase)
    # Consolidate synonymous, contained, and weak-modifier variants before the
    # model chooses URLs. This lets the model select 10 genuinely distinct
    # spokes instead of selecting duplicates that are removed only afterward.
    canonical: list[dict[str, Any]] = []
    main_item = next((dict(item) for item in prepared if item["phrase"] == main), {
        "phrase": main,
        "type": "primary",
        "h_tags": [],
    })
    canonical.append(main_item)
    for item in prepared:
        phrase = item["phrase"]
        if phrase == main:
            continue
        destination = next(
            (kept for kept in canonical if _hub_same_page_intent(phrase, kept["phrase"])),
            None,
        )
        if destination is None:
            canonical.append(item)
            continue
        destination["h_tags"] = list(dict.fromkeys([
            *(destination.get("h_tags") or []),
            phrase,
            *(item.get("h_tags") or []),
        ]))
    return canonical


def _append_h2s(spoke: str, extras: list[str]) -> str:
    extras = list(dict.fromkeys(extra for extra in extras if extra))
    if not extras:
        return spoke
    if "[Include:" in spoke:
        return spoke.rstrip("]") + f", {', '.join(extras)}]"
    if "[Include H2:" in spoke:
        return spoke.replace("[Include H2:", "[Include:").rstrip("]") + f", {', '.join(extras)}]"
    return spoke + f" [Include: {', '.join(extras)}]"


def _apply_hub_h2_plan(payload: dict[str, Any], keywords: list[dict[str, Any]]) -> dict[str, Any]:
    """Attach pre-approved H2 variants even when the model omits them."""
    from nlp.keywords import clean_phrase

    planned = {
        clean_phrase(str(item.get("phrase") or "")): [
            clean_phrase(str(value)) for value in (item.get("h_tags") or []) if clean_phrase(str(value))
        ]
        for item in keywords
        if item.get("h_tags")
    }
    for hub in payload.get("hubs", []) if isinstance(payload, dict) else []:
        if not isinstance(hub, dict) or "NOISE" in str(hub.get("hub_title", "")).upper():
            continue
        for node in [hub, *(hub.get("sub_silos") or [])]:
            if not isinstance(node, dict):
                continue
            target = clean_phrase(str(node.get("target_keyword") or ""))
            if planned.get(target):
                node["h2_keywords"] = list(dict.fromkeys([
                    *(node.get("h2_keywords") or []), *planned[target]
                ]))
            for layer, spokes in (node.get("layers") or {}).items():
                if not isinstance(spokes, list):
                    continue
                for index, spoke in enumerate(spokes):
                    match = re.search(r"\(Target Keyword:\s*(.*?)\)", str(spoke), re.IGNORECASE)
                    spoke_target = clean_phrase(match.group(1)) if match else ""
                    if planned.get(spoke_target):
                        spokes[index] = _append_h2s(str(spoke), planned[spoke_target])
    return payload


def _legacy_build_hub_spoke_fallback(
    keywords: list[dict[str, Any]],
    main_keyword: str,
) -> dict[str, Any]:
    """Build a valid map deterministically when the model violates constraints."""
    from nlp.keywords import clean_phrase

    keywords = _prepare_hub_page_keywords(keywords, main_keyword)
    main = clean_phrase(main_keyword) or "core topic"
    entities: list[str] = []
    unique: list[str] = []
    merged_h2s: dict[str, list[str]] = {}
    main_h2s: list[str] = []
    seen_slugs = {_hub_slug(main)}

    for item in keywords:
        phrase = clean_phrase(str(item.get("phrase") or ""))
        if not phrase or phrase == main:
            if phrase == main:
                main_h2s.extend(item.get("h_tags") or [])
            continue
        if item.get("type") == "entity":
            if phrase not in entities:
                entities.append(phrase)
            continue
        merged_h2s.setdefault(phrase, []).extend(item.get("h_tags") or [])
        slug = _hub_slug(phrase)
        if slug == _hub_slug(main) or _hub_intent_similarity(phrase, main) >= 0.60:
            main_h2s.append(phrase)
            main_h2s.extend(item.get("h_tags") or [])
            continue
        duplicate_of = next(
            (
                kept for kept in unique
                if slug == _hub_slug(kept) or _hub_intent_similarity(phrase, kept) >= 0.60
            ),
            None,
        )
        if duplicate_of:
            merged_h2s.setdefault(duplicate_of, []).append(phrase)
            continue
        if slug and slug not in seen_slugs:
            unique.append(phrase)
            seen_slugs.add(slug)

    # A silo target has its own URL, so reserve one keyword per silo in addition
    # to the required eight article targets.
    # A sub-silo is another indexable pillar page. Create one only when enough
    # genuinely distinct page intents remain to support it.
    silo_count = min(5, len(unique) // 12)

    master = {
        "hub_title": f"📍 MASTER HUB: {main.title()}",
        "target_keyword": main,
        "h2_keywords": list(dict.fromkeys(main_h2s)),
        "layers": {},
        "sub_silos": [],
    }
    if not silo_count:
        # Small maps remain useful without manufacturing an underfilled silo.
        master["layers"] = {
            "🧱 Foundations": [
                _append_h2s(
                    f"{phrase.title()} (Target Keyword: {phrase})",
                    merged_h2s.get(phrase, []),
                ) for phrase in unique
            ]
        }
        if entities and master["layers"]["🧱 Foundations"]:
            master["layers"]["🧱 Foundations"][0] = _append_h2s(
                master["layers"]["🧱 Foundations"][0], entities
            )
        elif entities:
            master["h2_keywords"] = list(dict.fromkeys([*master["h2_keywords"], *entities]))
        return {"_planning_thought": "Built a compact map from the supplied keywords.", "hubs": [master]}

    # Choose maximally different centers, then assign every remaining phrase to
    # its closest center while keeping enough room for balanced, valid silos.
    centers = [unique[0]]
    while len(centers) < silo_count:
        remaining = [phrase for phrase in unique if phrase not in centers]
        centers.append(max(remaining, key=lambda phrase: min(_hub_intent_similarity(phrase, center) for center in centers)))
    articles = [phrase for phrase in unique if phrase not in centers]
    groups: list[list[str]] = [[] for _ in centers]
    max_group = (len(articles) + silo_count - 1) // silo_count
    for phrase in articles:
        available = [index for index, group in enumerate(groups) if len(group) < max_group]
        best = max(available, key=lambda index: (_hub_intent_similarity(phrase, centers[index]), -len(groups[index])))
        groups[best].append(phrase)

    layer_names = (
        "🧱 Foundations",
        "⚙️ Action",
        "💰 Money",
        "⚡️ ZERO COMPETITION QUICK-WINS",
    )
    money_words = {"best", "price", "pricing", "cost", "review", "reviews", "versus", "vs", "alternative", "alternatives"}
    action_words = {"how", "guide", "tutorial", "setup", "create", "make", "use", "using", "steps"}

    def preferred_layer(phrase: str, position: int) -> str:
        words = set(clean_phrase(phrase).split())
        if words & money_words:
            return layer_names[2]
        if words & action_words:
            return layer_names[1]
        if len(words) >= 5 or words & {"why", "when", "problem", "fix", "tips"}:
            return layer_names[3]
        return layer_names[position % 4]

    for index, (center, group) in enumerate(zip(centers, groups), 1):
        layers = {name: [] for name in layer_names}
        for position, phrase in enumerate(group):
            # Seed the four mandatory layers once, then classify by intent.
            layer = layer_names[position] if position < 4 else preferred_layer(phrase, position)
            extras = list(dict.fromkeys(merged_h2s.get(phrase, [])))
            spoke = _append_h2s(f"{phrase.title()} (Target Keyword: {phrase})", extras)
            layers[layer].append(spoke)
        master["sub_silos"].append({
            "hub_title": f"🪐 SUB-SILO {index}: {center.title()}",
            "target_keyword": center,
            "layers": layers,
        })

    # Entities are headings, never URLs. Attach each to the closest article.
    for entity in entities:
        best_node = None
        best_position = None
        best_score = -1.0
        for node in [master, *master["sub_silos"]]:
            for layer, spokes in node["layers"].items():
                for position, spoke in enumerate(spokes):
                    target_match = re.search(r"\(Target Keyword:\s*(.*?)\)", spoke, re.IGNORECASE)
                    score = _hub_intent_similarity(entity, target_match.group(1) if target_match else spoke)
                    if score > best_score:
                        best_node, best_position, best_score = spokes, position, score
        if best_node is not None and best_position is not None:
            if "[Include:" in best_node[best_position]:
                best_node[best_position] = best_node[best_position].rstrip("]") + f", {entity}]"
            else:
                best_node[best_position] = _append_h2s(best_node[best_position], [entity])
        else:
            master["h2_keywords"] = list(dict.fromkeys([*master["h2_keywords"], entity]))

    return {
        "_planning_thought": f"Built {silo_count} balanced sub-silos and merged duplicate intents into H2 sections.",
        "_deduplication_check": {
            "unique_slugs": "Checked",
            "semantic_intents": "Checked",
            "entity_pages": "Converted to H2 sections",
        },
        "hubs": [master],
    }


def _hub_spoke_category(phrase: str) -> str:
    words = set(_hub_intent_tokens(phrase))
    lowered = phrase.lower()
    if words & {"best", "price", "pricing", "cost", "review", "versus", "alternative"} or " vs " in lowered:
        return "Software comparisons & commercial intent"
    if words & {"how", "guide", "tutorial", "setup", "create", "make", "use"}:
        return "How-to guides & tutorials"
    if words & {"symbol", "meaning", "standard", "reference", "chart"}:
        return "Reference guides"
    if words & {"example", "template", "project", "application"}:
        return "Examples & use cases"
    return "Educational topics"


ARCHITECTURE_WRITING_STANDARDS = [
    "Answer the search intent directly before adding background.",
    "Use active voice, plain language, precise claims, and no filler.",
    "Use the primary keyword naturally in the H1, introduction, and relevant headings.",
    "Open with an implicit definition, then explain the main benefits and uses in the same order as the article.",
    "Define abbreviations on first use and use entities in their correct context.",
    "Match question headings with immediate explicit answers; start boolean answers with Yes or No.",
    "Use concrete examples, helpful analogies, useful tables or steps, and verifiable facts without inventing evidence.",
    "Quantify claims when reliable numbers exist, keep list grammar parallel, and answer place, time, and method questions in the requested context first.",
    "Use a natural expert tone and make every word serve the reader.",
    "Avoid vague hype, keyword stuffing, unclear pronouns, repetitive conclusions, and AI-style filler phrases.",
]


def _allowed_hub_target(target: str, allowed: set[str], main_keyword: str) -> bool:
    """Allow supplied targets and a broader parent that consolidates variants."""
    from nlp.keywords import clean_phrase

    target = clean_phrase(target)
    if not target:
        return False
    if target == clean_phrase(main_keyword) or target in allowed:
        return True
    prefix = target + " "
    return sum(1 for keyword in allowed if keyword.startswith(prefix)) >= 2


def _sanitize_hub_keyword_values(values: Any, allowed: set[str], excluded: str = "") -> list[str]:
    from nlp.keywords import clean_phrase

    excluded = clean_phrase(excluded)
    return list(dict.fromkeys(
        phrase for value in (values or [])
        if (phrase := clean_phrase(str(value))) in allowed and phrase != excluded
    ))


def _article_keyword_placements(article: dict[str, Any], allowed: set[str]) -> list[str]:
    values: list[Any] = [*(article.get("targeted_keywords") or []), *(article.get("entity_terms") or [])]
    for section in article.get("h2_sections", []) or []:
        if isinstance(section, dict):
            values.extend(section.get("targeted_keywords_placed_here") or [])
    for faq in article.get("faq_schema_questions", []) or []:
        if isinstance(faq, dict):
            values.extend(faq.get("targeted_keywords_placed_here") or [])
    return _sanitize_hub_keyword_values(values, allowed)


def _sanitize_detailed_hub_plan(
    payload: dict[str, Any],
    keywords: list[dict[str, Any]],
    main_keyword: str,
) -> dict[str, Any]:
    """Mechanically remove irrelevant placements and competing page intents."""
    from nlp.keywords import clean_phrase, keyword_terms

    if not isinstance(payload, dict) or not isinstance(payload.get("master_hub"), dict):
        return payload
    allowed = {
        clean_phrase(str(item.get("phrase") or "")) for item in keywords
        if clean_phrase(str(item.get("phrase") or ""))
    }
    main = clean_phrase(main_keyword) or "core topic"
    allowed.add(main)
    all_topic_terms = set().union(*(keyword_terms(value, min_len=2) for value in allowed)) if allowed else set()
    removed_irrelevant: list[str] = []
    duplicate_redirects: dict[str, str] = {}

    def sanitize_article(article: dict[str, Any], target: str) -> None:
        article["target_keyword"] = target
        article["slug"] = f"/{_hub_slug(target)}/"
        article["targeted_keywords"] = _sanitize_hub_keyword_values(
            article.get("targeted_keywords"), allowed, target
        )
        article["entity_terms"] = _sanitize_hub_keyword_values(article.get("entity_terms"), allowed, target)
        clean_sections = []
        for section in article.get("h2_sections", []) or []:
            if not isinstance(section, dict):
                continue
            placements = _sanitize_hub_keyword_values(
                section.get("targeted_keywords_placed_here"), allowed, target
            )
            heading = str(section.get("h2_heading") or "").strip()
            heading_terms = keyword_terms(heading, min_len=2)
            if heading and (not heading_terms or heading_terms & all_topic_terms or placements):
                section["targeted_keywords_placed_here"] = placements
                clean_sections.append(section)
        article["h2_sections"] = clean_sections
        clean_faqs = []
        for faq in article.get("faq_schema_questions", []) or []:
            if not isinstance(faq, dict):
                continue
            placements = _sanitize_hub_keyword_values(
                faq.get("targeted_keywords_placed_here"), allowed, target
            )
            question = str(faq.get("question") or "").strip()
            question_terms = keyword_terms(question, min_len=2)
            if question and (not question_terms or question_terms & all_topic_terms or placements):
                faq["targeted_keywords_placed_here"] = placements
                clean_faqs.append(faq)
        article["faq_schema_questions"] = clean_faqs
        title = str(article.get("article_title") or target.title()).strip()
        if keyword_terms(title, min_len=2) and not keyword_terms(title, min_len=2) & (
            keyword_terms(target, min_len=2) | all_topic_terms
        ):
            title = target.title()
        article["article_title"] = title or target.title()

    master = payload["master_hub"]
    master["target_keyword"] = main
    sanitize_article(master, main)
    kept: list[dict[str, Any]] = []

    def merge_duplicate(destination: dict[str, Any], source: dict[str, Any], source_target: str) -> None:
        placements = _article_keyword_placements(source, allowed)
        if source_target in allowed and source_target != clean_phrase(str(destination.get("target_keyword") or "")):
            placements.insert(0, source_target)
        placements = list(dict.fromkeys(placements))
        if not placements:
            return
        sections = destination.setdefault("h2_sections", [])
        if not sections:
            sections.append({
                "h2_heading": "Related searches to cover",
                "section_definition": "Cover these overlapping searches on this page instead of creating competing URLs.",
                "targeted_keywords_placed_here": [],
            })
        current = sections[0].setdefault("targeted_keywords_placed_here", [])
        sections[0]["targeted_keywords_placed_here"] = list(dict.fromkeys([*current, *placements]))

    for raw_article in payload.get("spokes", []) or []:
        if not isinstance(raw_article, dict):
            continue
        article = dict(raw_article)
        target = clean_phrase(str(article.get("target_keyword") or ""))
        if not _allowed_hub_target(target, allowed, main):
            if target:
                removed_irrelevant.append(target)
            continue
        sanitize_article(article, target)
        slug = _hub_slug(target)
        title_key = clean_phrase(str(article.get("article_title") or target))
        fingerprint = tuple(sorted(_hub_intent_tokens(target)))
        duplicate_index = next((
            index for index, existing in enumerate(kept)
            if target == clean_phrase(str(existing.get("target_keyword") or ""))
            or slug == _hub_slug(str(existing.get("target_keyword") or ""))
            or title_key == clean_phrase(str(existing.get("article_title") or ""))
            or fingerprint == tuple(sorted(_hub_intent_tokens(str(existing.get("target_keyword") or ""))))
            or _hub_same_page_intent(target, str(existing.get("target_keyword") or ""))
        ), None)
        duplicates_master = (
            target == main
            or slug == _hub_slug(main)
            or title_key == clean_phrase(str(master.get("article_title") or main))
            or fingerprint == tuple(sorted(_hub_intent_tokens(main)))
            or _hub_same_page_intent(target, main)
        )
        if duplicates_master:
            merge_duplicate(master, article, target)
            duplicate_redirects[target] = main
            continue
        if duplicate_index is not None:
            destination = kept[duplicate_index]
            destination_target = clean_phrase(str(destination.get("target_keyword") or ""))
            merge_duplicate(destination, article, target)
            duplicate_redirects[target] = destination_target
            continue
        kept.append(article)

    valid_targets = {main, *(clean_phrase(str(article.get("target_keyword") or "")) for article in kept)}
    for article in [master, *kept]:
        links = []
        for value in article.get("internal_links", []) or []:
            target = clean_phrase(str(value))
            target = duplicate_redirects.get(target, target)
            if target in valid_targets and target != clean_phrase(str(article.get("target_keyword") or "")):
                links.append(target)
        article["internal_links"] = list(dict.fromkeys(links))

    payload["spokes"] = kept
    payload["filtered_irrelevant_keywords"] = list(dict.fromkeys([
        *_sanitize_hub_keyword_values(payload.get("filtered_irrelevant_keywords"), allowed),
        *removed_irrelevant,
    ]))
    payload["_deduplication_check"] = {
        "unique_target_keywords": "Checked",
        "unique_titles": "Checked",
        "unique_slugs": "Checked",
        "semantic_intents": "Checked",
        "duplicates_removed": len(duplicate_redirects),
    }
    return payload


def _deepseek_plan_to_hub_schema(payload: dict[str, Any], main_keyword: str) -> dict[str, Any]:
    """Add the visual-card schema while retaining DeepSeek's detailed editorial plan."""
    from nlp.keywords import clean_phrase

    if not isinstance(payload.get("master_hub"), dict):
        return payload
    payload.pop("hubs", None)
    master_plan = payload["master_hub"]
    main = clean_phrase(str(master_plan.get("target_keyword") or main_keyword)) or clean_phrase(main_keyword)
    master_plan["target_keyword"] = main
    # Generate URLs from normalized targets so model creativity can never
    # introduce malformed or duplicate slugs.
    master_plan["slug"] = f"/{_hub_slug(main)}/"
    master_plan["page_type"] = str(master_plan.get("page_type") or ("tool" if any(
        word in main.split() for word in ("tool", "software", "calculator", "generator", "maker", "builder")
    ) else "article")).lower()
    master_plan.setdefault("writing_instructions", "Follow the global writing standards, satisfy the primary intent immediately, and make this the definitive navigation and conversion page for the topic.")
    master_plan.setdefault("tool_functions", [])
    if master_plan["page_type"] == "tool" and not master_plan["tool_functions"]:
        master_plan["tool_functions"] = _default_architecture_tool_functions(main)
    payload.setdefault("writing_standards", ARCHITECTURE_WRITING_STANDARDS)
    master_keywords = [
        clean_phrase(str(value)) for value in (master_plan.get("targeted_keywords") or [])
        if clean_phrase(str(value)) and clean_phrase(str(value)) != main
    ]
    for section in master_plan.get("h2_sections", []) or []:
        if isinstance(section, dict):
            master_keywords.extend(
                clean_phrase(str(value)) for value in section.get("targeted_keywords_placed_here", []) or []
                if clean_phrase(str(value)) and clean_phrase(str(value)) != main
            )
    for faq in master_plan.get("faq_schema_questions", []) or []:
        if isinstance(faq, dict):
            master_keywords.extend(
                clean_phrase(str(value)) for value in faq.get("targeted_keywords_placed_here", []) or []
                if clean_phrase(str(value)) and clean_phrase(str(value)) != main
            )
    master_keywords.extend(
        clean_phrase(str(value)) for value in master_plan.get("entity_terms", []) or []
        if clean_phrase(str(value)) and clean_phrase(str(value)) != main
    )
    layers: dict[str, list[str]] = {}
    for article in payload.get("spokes", []) or []:
        if not isinstance(article, dict):
            continue
        target = clean_phrase(str(article.get("target_keyword") or ""))
        if not target:
            continue
        article["target_keyword"] = target
        article["slug"] = f"/{_hub_slug(target)}/"
        article["page_type"] = str(article.get("page_type") or ("tool" if any(
            word in target.split() for word in ("tool", "software", "calculator", "generator", "maker", "builder")
        ) else "article")).lower()
        article.setdefault("writing_instructions", "Follow the global writing standards, answer the page's distinct intent immediately, and avoid repeating the Master Hub or another spoke.")
        article.setdefault("tool_functions", [])
        if article["page_type"] == "tool" and not article["tool_functions"]:
            article["tool_functions"] = _default_architecture_tool_functions(target)
        included: list[str] = []
        for section in article.get("h2_sections", []) or []:
            if isinstance(section, dict):
                included.extend(section.get("targeted_keywords_placed_here") or [])
        for faq in article.get("faq_schema_questions", []) or []:
            if isinstance(faq, dict):
                included.extend(faq.get("targeted_keywords_placed_here") or [])
        included.extend(article.get("entity_terms") or [])
        included = list(dict.fromkeys(
            clean_phrase(str(value)) for value in included
            if clean_phrase(str(value)) and clean_phrase(str(value)) != target
        ))
        title = str(article.get("article_title") or target.title()).strip()
        spoke = _append_h2s(f"{title} (Target Keyword: {target})", included)
        category = str(article.get("spoke_category") or _hub_spoke_category(target))
        layers.setdefault(category, []).append(spoke)
    return {
        **payload,
        "hubs": [{
            "hub_title": f"📍 MASTER HUB: {str(master_plan.get('article_title') or main.title())}",
            "target_keyword": main,
            "h2_keywords": list(dict.fromkeys(master_keywords)),
            "content_brief": str(master_plan.get("content_brief") or ""),
            "layers": layers,
            "sub_silos": [],
        }],
    }


def _default_architecture_tool_functions(target: str) -> list[str]:
    return [
        f"Provide the core interactive result promised by the '{target}' search intent.",
        "Collect only the inputs required to generate the result and validate them with clear inline feedback.",
        "Let the user edit, reset, copy, download, or export the result where the output format permits it.",
        "Work on mobile and desktop, preserve accessible labels, and show a clear next action after generation.",
    ]


def build_hub_spoke_fallback(
    keywords: list[dict[str, Any]],
    main_keyword: str,
) -> dict[str, Any]:
    """Build one Master Hub and 10-20 flat spokes if the provider is unavailable."""
    from nlp.keywords import clean_phrase

    keywords = _prepare_hub_page_keywords(keywords, main_keyword)
    main = clean_phrase(main_keyword) or "core topic"
    entities = list(dict.fromkeys(
        clean_phrase(str(item.get("phrase") or "")) for item in keywords
        if item.get("type") == "entity" and clean_phrase(str(item.get("phrase") or ""))
    ))
    phrases = list(dict.fromkeys(
        clean_phrase(str(item.get("phrase") or "")) for item in keywords
        if item.get("type") != "entity" and clean_phrase(str(item.get("phrase") or "")) != main
    ))
    if len(phrases) < 10:
        phrases.extend(
            phrase for phrase in (
                f"{main} guide", f"how to use {main}", f"best {main}", f"{main} examples",
                f"{main} features", f"{main} tutorial", f"{main} comparison", f"{main} for beginners",
                f"{main} use cases", f"{main} troubleshooting",
            ) if phrase not in phrases
        )
    spoke_count = min(20, max(10, (len(phrases) + 3) // 4))
    centers = phrases[:spoke_count]
    assignments: dict[str, list[str]] = {center: [] for center in centers}
    for phrase in phrases[spoke_count:]:
        center = max(centers, key=lambda candidate: _hub_intent_similarity(phrase, candidate))
        assignments[center].append(phrase)
    entity_assignments: dict[str, list[str]] = {center: [] for center in centers}
    for entity in entities:
        center = max(centers, key=lambda candidate: _hub_intent_similarity(entity, candidate))
        entity_assignments[center].append(entity)

    spokes = []
    for center in centers:
        included = assignments[center]
        faq_keywords = [phrase for phrase in included if phrase.split()[0] in {"what", "why", "when", "where", "can", "does", "is", "are"}]
        h2_keywords = [phrase for phrase in included if phrase not in faq_keywords]
        is_tool = any(word in center.split() for word in ("tool", "software", "calculator", "generator", "maker", "builder"))
        spokes.append({
            "spoke_category": _hub_spoke_category(center),
            "article_title": center.title(),
            "target_keyword": center,
            "slug": f"/{_hub_slug(center)}/",
            "page_type": "tool" if is_tool else "article",
            "word_count_suggestion": 2000,
            "content_brief": f"Satisfy the search intent for {center} and connect readers to the {main} hub.",
            "h2_sections": [{
                "h2_heading": "Related questions and subtopics",
                "section_definition": "Cover these closely related terms together only where they require a substantive section.",
                "targeted_keywords_placed_here": h2_keywords,
            }] if h2_keywords else [],
            "faq_schema_questions": [
                {"question": phrase.title() + "?", "targeted_keywords_placed_here": [phrase]}
                for phrase in faq_keywords
            ],
            "entity_terms": entity_assignments[center],
            "tool_functions": _default_architecture_tool_functions(center) if is_tool else [],
            "internal_links": [main],
            "writing_instructions": "Answer the target intent immediately. Use active voice, plain language, specific examples, clear heading-answer alignment, natural entities, and no filler or unsupported claims.",
        })
    plan = {
        "filtered_irrelevant_keywords": [],
        "total_relevant_keywords_covered": len(phrases) + len(entities) + 1,
        "master_hub": {
            "article_title": main.title(),
            "target_keyword": main,
            "slug": f"/{_hub_slug(main)}/",
            "page_type": "tool" if any(word in main.split() for word in ("tool", "software", "calculator", "generator", "maker", "builder")) else "article",
            "word_count_suggestion": 3500,
            "content_brief": f"The definitive home-page guide and primary conversion page for {main}.",
            "targeted_keywords": [main],
            "tool_functions": _default_architecture_tool_functions(main) if any(word in main.split() for word in ("tool", "software", "calculator", "generator", "maker", "builder")) else [],
            "h2_sections": [{
                "h2_heading": f"What is {main.title()}?",
                "section_definition": "Define the central topic, establish its value, and route readers to the most relevant detailed spokes.",
                "targeted_keywords_placed_here": [],
            }],
            "faq_schema_questions": [],
            "entity_terms": [],
            "internal_links": centers,
            "writing_instructions": "Answer the main intent immediately, use a precise H1 and descriptive H2s, write in active voice, remove filler, use entities naturally, and make every section useful to the target reader.",
        },
        "spokes": spokes,
        "interlinking_strategy": "Every spoke links to the Master Hub. Related spokes link to one another where the next article answers the reader's natural follow-up question.",
        "writing_standards": ARCHITECTURE_WRITING_STANDARDS,
    }
    plan = _sanitize_detailed_hub_plan(plan, keywords, main)
    return _deepseek_plan_to_hub_schema(plan, main)


def _validate_hub_and_spoke(
    payload: dict,
    total_kws: int,
    main_keyword: str | None = None,
    allowed_keywords: set[str] | None = None,
) -> str | None:
    """Validate constraints that must hold regardless of model compliance."""
    from nlp.keywords import clean_phrase

    hubs = payload.get("hubs") if isinstance(payload, dict) else None
    if not isinstance(hubs, list) or not hubs:
        return "Missing or empty 'hubs' array."
    content_hubs = [hub for hub in hubs if isinstance(hub, dict) and "NOISE" not in str(hub.get("hub_title", "")).upper()]
    if len(content_hubs) != 1:
        return f"Expected exactly one master hub, received {len(content_hubs)}."

    master = content_hubs[0]
    if main_keyword and set(clean_phrase(str(master.get("target_keyword") or "")).split()) != set(clean_phrase(main_keyword).split()):
        return "Master hub target_keyword must match the primary seed keyword."

    sub_silos = master.get("sub_silos", [])
    if not isinstance(sub_silos, list):
        return "Master hub sub_silos must be an array."
    if sub_silos:
        return "Use a flat plan with one Master Hub and no nested sub-silos."
    layers = master.get("layers", {})
    spoke_count = sum(len(items) for items in layers.values() if isinstance(items, list)) if isinstance(layers, dict) else 0
    if not 10 <= spoke_count <= 20:
        return f"The plan must contain 10 to 20 spokes; received {spoke_count}."
    seen_targets: set[str] = set()
    seen_slugs: set[str] = set()
    seen_titles: set[str] = set()
    seen_fingerprints: set[tuple[str, ...]] = set()
    seen_intents: list[str] = []
    entity_keywords = {
        clean_phrase(keyword[7:]) for keyword in (allowed_keywords or set()) if keyword.startswith("entity:")
    }
    allowed = {
        clean_phrase(keyword.removeprefix("entity:")) for keyword in (allowed_keywords or set())
    }

    def is_allowed_target(target: str) -> bool:
        if not allowed or target in allowed:
            return True
        if len(allowed) < 10 and main_keyword and _hub_intent_similarity(target, main_keyword) > 0:
            return True
        # A shared parent is permitted when it deterministically consolidates
        # two or more supplied modifier variants onto one stronger URL.
        prefix = target + " "
        return sum(1 for keyword in allowed if keyword.startswith(prefix)) >= 2

    master_target = clean_phrase(str(master.get("target_keyword") or ""))
    seen_slugs.add(_hub_slug(master_target))
    seen_titles.add(master_target)
    seen_fingerprints.add(tuple(sorted(_hub_intent_tokens(master_target))))
    seen_intents.append(master_target)

    def validate_layers(node: dict, label: str, minimum: int = 0) -> str | None:
        layers = node.get("layers", {})
        if not isinstance(layers, dict):
            return f"{label} layers must be an object."
        count = sum(len(items) for items in layers.values() if isinstance(items, list))
        if count < minimum:
            return f"{label} has {count} articles; at least {minimum} are required."
        if minimum:
            names = " ".join(str(name).lower() for name in layers)
            for required in ("foundation", "action", "money", "quick"):
                if required not in names:
                    return f"{label} is missing its {required} layer."
        for items in layers.values():
            if not isinstance(items, list):
                return f"{label} layer values must be arrays."
            for spoke in items:
                matches = re.findall(r"\(Target Keyword:\s*(.*?)\)", str(spoke), re.IGNORECASE)
                if len(matches) != 1:
                    return f"Every {label} spoke must contain exactly one Target Keyword."
                target = clean_phrase(matches[0])
                if target in seen_targets:
                    return f"Duplicate target keyword: {target}."
                slug = _hub_slug(target)
                if slug in seen_slugs:
                    return f"Duplicate URL slug: {slug}."
                title = clean_phrase(str(spoke).split("(Target Keyword:", 1)[0].replace("[Tool]", ""))
                if title in seen_titles:
                    return f"Duplicate article title: {title}."
                fingerprint = tuple(sorted(_hub_intent_tokens(target)))
                if fingerprint in seen_fingerprints:
                    return f"Duplicate keyword intent: {target}."
                duplicate_intent = next(
                    (existing for existing in seen_intents if _hub_same_page_intent(target, existing)),
                    None,
                )
                if duplicate_intent:
                    return f"Cannibalizing keyword intent: {target} overlaps {duplicate_intent}."
                if target in entity_keywords:
                    return f"Entity keyword cannot be a standalone spoke: {target}."
                if not is_allowed_target(target):
                    return f"Spoke target keyword was not supplied by the scan: {target}."
                seen_targets.add(target)
                seen_slugs.add(slug)
                seen_titles.add(title)
                seen_fingerprints.add(fingerprint)
                seen_intents.append(target)
        return None

    error = validate_layers(master, "Master hub")
    if error:
        return error
    for index, silo in enumerate(sub_silos, 1):
        if not isinstance(silo, dict):
            return f"Sub-silo {index} must be an object."
        silo_target = clean_phrase(str(silo.get("target_keyword") or ""))
        if silo_target == clean_phrase(str(master.get("target_keyword") or "")):
            return f"Sub-silo {index} duplicates the master target keyword."
        silo_slug = _hub_slug(silo_target)
        if not silo_target or silo_slug in seen_slugs:
            return f"Sub-silo {index} has a duplicate or empty slug."
        if silo_target in entity_keywords:
            return f"Entity keyword cannot be a sub-silo target: {silo_target}."
        if not is_allowed_target(silo_target):
            return f"Sub-silo target keyword was not supplied by the scan: {silo_target}."
        seen_slugs.add(silo_slug)
        seen_intents.append(silo_target)
        error = validate_layers(silo, f"Sub-silo {index}")
        if error:
            return error
    return None


async def _legacy_cluster_hub_and_spoke(
    keywords: list[dict[str, Any]], 
    main_keyword: str = "your core topic",
    audit_summary: str | None = None
) -> dict[str, Any] | None:
    """Cluster keywords into categorized Hub and Spoke architectures, strictly avoiding cannibalization."""
    if not keywords:
        return None

    trimmed = _prepare_hub_page_keywords(keywords[:500], main_keyword)
    if not is_ai_configured():
        return build_hub_spoke_fallback(trimmed, main_keyword)
    
    audit_context = f"""
[WEBSITE CONTEXT (CRITICAL)]
You MUST filter and organize the keywords based on this actual website context. 
If a keyword does not make sense for a website with this profile, do NOT include it in the hubs.
{audit_summary}
""" if audit_summary else ""

    prompt = f"""
Take a raw, flat Hub-and-Spoke list of keywords and transform it into a visually optimized, layered, ranking-ready SEO architecture.
You are a Senior SEO Content Strategist and Topical Authority Architect.

{audit_context}

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
- Use 0 to 5 Sub-Silos. Create a Sub-Silo only when its broad target deserves an indexable pillar URL.
- There is NO minimum article quota. Never manufacture thin pages to fill a silo or layer.
- A keyword deserves a separate page only when its search intent needs a substantially different answer.

STEP 4: PAGE-INTENT CONSOLIDATION
- Treat every item in Target Keywords List as one approved page target.
- Items can contain `h_tags`. Those are related queries that MUST be covered as H2 sections on that page, never separate URLs.
- Audience, use-case, standard, format, feature, and minor modifier variants belong as H2s when one broader page can answer them.
- Example: "circuit diagram symbols for ports", "...for nodes", and "...for ANSI" belong under one "circuit diagram symbols" page.
- Do not turn every keyword into a spoke. A spoke represents an indexable article/page, not a keyword row.

STEP 5: COMMERCIAL CONSOLIDATION
- If you are generating Commercial/Money pages, you are only allowed to create ONE primary commercial URL per distinct product category.
- DO NOT generate separate URLs for micro-audiences (e.g., "best apps for professionals", "best apps for students").
- Instead, create ONE master commercial page and append the micro-audiences using `[Include: ...]`. Delete the extra spokes.

STEP 6: BEGINNER PAGE LIMIT
- If you are generating Action or Foundation pages for beginners, limit to a maximum of TWO (2) beginner pages per silo:
  - Page 1 (The Theory): "[Topic] Basics"
  - Page 2 (The Action): "How to use [Topic] / Tutorial"
- Consolidate any extras into H2 subheadings on these two pages using `[Include: ...]`.

STEP 7: INTENT TAGS & ENTITIES
- If a keyword is a tool/calculator/software, output it with a [Tool] tag in the title.
- ANTI-CANNIBALIZATION: If multiple variations share the same search intent, keep the broadest useful target and append the rest as `[Include: keyword]`.
- ENTITIES: If "type" == "entity", YOU ARE STRICTLY FORBIDDEN from creating a standalone article. Append it as `[Include: entity]` to the most relevant article.

[OUTPUT SCHEMA - STRICT JSON ONLY]
{{
  "_planning_thought": "Explain which search intents deserve separate URLs and which variants were consolidated into H2 sections.",
  "_deduplication_check": {{
    "layer_1_swapped_words": "Checked: Did any URLs swap words? If yes, I deleted the weaker one.",
    "layer_2_synonyms": "Checked: Did any URLs use synonyms like 'understanding' vs 'meanings', 'test' vs 'quiz', 'guide' vs 'tutorial'? If yes, I merged them.",
    "layer_3_overlap_70_percent": "Checked: Do any URLs share more than 70% of the same words (e.g., 'how-to-draw' vs 'step-by-step-draw')? If yes, I deleted the weaker one."
  }},
  "hubs": [
    {{
      "hub_title": "📍 MASTER HUB: [Broadest Search Intent / Topic]",
      "target_keyword": "[exact keyword]",
      "h2_keywords": ["related query covered on this page"],
      "layers": {{
        "🧱 FOUNDATION SPOKES (Authority)": ["[Compelling Article Title 1] (Target Keyword: [exact keyword 1])"],
        "⚙️ CORE STRATEGY": ["[Compelling Article Title 2] (Target Keyword: [exact keyword 2])"]
      }},
      "sub_silos": [
        {{
          "hub_title": "🪐 SUB-SILO 1: LEARNING HUB — [Sub-Topic Name]",
          "target_keyword": "[exact keyword]",
          "h2_keywords": ["related query covered on this pillar page"],
          "layers": {{
            "🧱 Foundations": ["[Compelling Article Title 3] (Target Keyword: [exact keyword 3])"],
            "⚙️ Action": ["[Compelling Article Title 4] (Target Keyword: [exact keyword 4]) [Include: related_keyword]"],
            "💰 Money": ["[Compelling Article Title 5] (Target Keyword: [exact keyword 5])"],
            "⚡️ ZERO COMPETITION QUICK-WINS": ["[Compelling Article Title 6] (Target Keyword: [exact keyword 6])"]
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
1. Creating separate URLs for keywords already supplied in an item's `h_tags`.
2. Creating thin pages solely to fill a layer or silo.
3. Giving two URLs the same or substantially overlapping search intent.

Target Keywords List:
{json.dumps(trimmed)}

Main Keywords (Create Master Hubs and Spokes using ONLY these):
{json.dumps([kw for kw in trimmed if kw.get("type") != "entity"])}

Entity Keywords (DO NOT CREATE SPOKES FOR THESE. Distribute and append them as [Include: entity] to the most relevant Spokes created above):
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
                payload = _apply_hub_h2_plan(payload, trimmed)
                tagged_allowed = {
                    ("entity:" if kw.get("type") == "entity" else "") + str(kw.get("phrase") or "")
                    for kw in trimmed
                }
                err = _validate_hub_and_spoke(
                    payload,
                    len(trimmed),
                    main_keyword=main_keyword,
                    allowed_keywords=tagged_allowed,
                )
                if err and attempt < max_retries - 1:
                    logger.warning(f"Validation failed on attempt {attempt+1}: {err}. Retrying...")
                    prompt += f"\n\n[SYSTEM FEEDBACK - ATTEMPT {attempt+1} FAILED]\nYour previous output was REJECTED because: {err}\nYou MUST fix this immediately."
                    continue
                if err:
                    logger.error("Hub-and-spoke output remained invalid: %s; using deterministic fallback", err)
                    break
                return payload
            logger.warning("Hub-and-spoke provider returned a non-object payload on attempt %d", attempt + 1)
        except Exception as exc:
            logger.error("Failed to cluster hub and spoke via %s on attempt %d: %s", ai_provider_name(), attempt+1, exc)
    fallback = build_hub_spoke_fallback(trimmed, main_keyword)
    tagged_allowed = {
        ("entity:" if kw.get("type") == "entity" else "") + str(kw.get("phrase") or "")
        for kw in trimmed
    }
    fallback_error = _validate_hub_and_spoke(
        fallback,
        len(trimmed),
        main_keyword=main_keyword,
        allowed_keywords=tagged_allowed,
    )
    if fallback_error:
        logger.error("Deterministic hub-and-spoke fallback failed validation: %s", fallback_error)
        return None
    return fallback


async def cluster_hub_and_spoke(
    keywords: list[dict[str, Any]],
    main_keyword: str = "your core topic",
    audit_summary: str | None = None,
) -> dict[str, Any] | None:
    """Create one Master Hub and 10-20 flat spokes using the DeepSeek plan contract."""
    if not keywords:
        return None

    trimmed = _prepare_hub_page_keywords(keywords[:500], main_keyword)
    if not is_ai_configured():
        return build_hub_spoke_fallback(trimmed, main_keyword)

    prompt = f"""
You are an elite SEO Architect and Content Strategist specializing in Hub-Spoke and Pillar-Cluster models.

Website context:
{audit_summary or "Infer the business context conservatively from the primary keyword and keyword list."}

Primary keyword: {main_keyword}
Raw keyword list:
{json.dumps(trimmed)}

Execute these steps in sequence:
1. FILTER: Treat the primary keyword/EMD as the central entity. Remove every keyword outside its two-hop topical neighborhood and every keyword that violates a hard boundary. Shared generic words do not prove relevance. Never keep an unrelated keyword to reach the article quota.
2. CLUSTER: Group every relevant keyword by search intent.
3. STRUCTURE: Build exactly 1 Master Hub and 10 to 20 strategically connected Spoke articles. The total plan must contain 11 to 21 articles. Use a flat plan with no nested hubs or sub-silos.
4. PREVENT CANNIBALIZATION: Each article must satisfy a distinct primary search intent. Tool synonyms such as maker, generator, software, app, builder, and visualizer share one page unless their required function is materially different. Electric/electronic/electrical, diagram/schematic/drawing, simple/basic, and tutorial/guide/overview variants share one page. Put overlapping and long-tail variants inside the strongest article as H2, H3, Entity, or FAQ placements.
5. STANDARDS: Never create individual articles for ANSI, IEC, DIN, JIS, UL, CE, FCC, IEEE, BS, or similar standards. Consolidate them under one relevant standards section or article.
6. MAP: Explicitly place every relevant keyword in one article as its Title/H1 target, H2, H3, Entity, or FAQ. Cover all relevant keywords.
7. INTERLINK: Create a useful authority loop between theory, tutorials, references, comparisons, and the Master Hub.

Return only this JSON object:
{{
  "filtered_irrelevant_keywords": ["removed keyword"],
  "total_relevant_keywords_covered": 0,
  "master_hub": {{
    "article_title": "Compelling home-page hub title",
    "target_keyword": "{main_keyword}",
    "slug": "/exact-clean-slug/",
    "page_type": "tool or article",
    "word_count_suggestion": 3500,
    "content_brief": "What this definitive hub must cover",
    "targeted_keywords": ["keywords assigned to the hub"],
    "tool_functions": ["required function when page_type is tool"],
    "h2_sections": [
      {{"h2_heading": "Useful heading", "section_definition": "What this section must explain and why", "targeted_keywords_placed_here": ["only keywords that need this heading"]}}
    ],
    "faq_schema_questions": [
      {{"question": "Relevant question?", "targeted_keywords_placed_here": ["assigned keyword"]}}
    ],
    "entity_terms": ["supporting term that belongs naturally in the copy"],
    "internal_links": ["target keyword of a spoke this page must link to"],
    "writing_instructions": "Page-specific instructions"
  }},
  "spokes": [
    {{
      "spoke_category": "Comparisons, Tutorials, References, Theory, or Use Cases",
      "article_title": "Compelling article title",
      "target_keyword": "one distinct primary keyword",
      "slug": "/exact-clean-slug/",
      "page_type": "article or tool",
      "word_count_suggestion": 2000,
      "content_brief": "Specific content focus and value to the website audience",
      "tool_functions": ["List concrete inputs, actions, validation, output, export, and UX functions when this is a tool page; otherwise return an empty array"],
      "h2_sections": [
        {{"h2_heading": "Useful heading", "section_definition": "What this section must explain and why", "targeted_keywords_placed_here": ["only keywords that need this heading"]}}
      ],
      "faq_schema_questions": [
        {{"question": "Relevant question?", "targeted_keywords_placed_here": ["assigned keyword"]}}
      ],
      "entity_terms": ["supporting term that belongs naturally in the copy"],
      "internal_links": ["master target keyword", "closely related spoke target keyword"],
      "writing_instructions": "Page-specific instructions derived from the writing standards"
    }}
  ],
  "interlinking_strategy": "A concrete authority-loop linking strategy",
  "writing_standards": {json.dumps(ARCHITECTURE_WRITING_STANDARDS)}
}}

Final checks: return 10-20 spokes, exactly one Master Hub, no duplicate target keywords, no nested silos, and no relevant keyword left unmapped.
"""
    tagged_allowed = {
        ("entity:" if kw.get("type") == "entity" else "") + str(kw.get("phrase") or "")
        for kw in trimmed
    }
    for attempt in range(3):
        try:
            raw_payload = await _achat_json(
                system_prompt="You are an elite SEO Architect. Follow the JSON contract exactly.",
                user_prompt=prompt,
                temperature=0.2,
                max_tokens=12000,
            )
            if not isinstance(raw_payload, dict):
                raise ValueError("Provider returned a non-object plan")
            raw_payload = _sanitize_detailed_hub_plan(raw_payload, trimmed, main_keyword)
            payload = _deepseek_plan_to_hub_schema(raw_payload, main_keyword)
            error = _validate_hub_and_spoke(
                payload,
                len(trimmed),
                main_keyword=main_keyword,
                allowed_keywords=tagged_allowed,
            )
            if not error:
                return payload
            logger.warning("Hub-spoke plan failed validation on attempt %s: %s", attempt + 1, error)
            prompt += f"\n\nYour previous plan was rejected: {error} Fix it and return the full JSON again."
        except Exception as exc:
            logger.warning("Hub-spoke generation failed on attempt %s: %s", attempt + 1, exc)

    fallback = build_hub_spoke_fallback(trimmed, main_keyword)
    fallback_error = _validate_hub_and_spoke(
        fallback,
        len(trimmed),
        main_keyword=main_keyword,
        allowed_keywords=tagged_allowed,
    )
    if fallback_error:
        logger.error("Hub-spoke fallback failed validation: %s", fallback_error)
        return None
    return fallback
