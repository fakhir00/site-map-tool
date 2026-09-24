"""SEO-specialist agent for building a complete, cannibalization-safe site architecture."""

from __future__ import annotations

import json
import logging
import math
import re
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import urlparse

from nlp.keywords import clean_phrase, is_publishable_keyword, looks_incomplete_search_query
from nlp.openrouter import _achat_json, is_ai_configured

logger = logging.getLogger(__name__)

WRITING_STANDARDS = [
    "Satisfy the assigned search intent directly and completely.",
    "Use plain expert language, verifiable claims, and no filler or keyword stuffing.",
    "Use supporting keywords only in the page to which the architecture assigns them.",
    "Give each indexable page a distinct purpose, title, H1, slug, and internal-link role.",
    "Link every spoke to the master hub and add lateral links only where they help the reader.",
]


class ArchitectureAgentError(RuntimeError):
    pass


def _clean_domain(value: str) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    return (parsed.hostname or "").removeprefix("www.")


def _domain_from_context(context: str) -> str:
    try:
        payload = json.loads(context) if context.strip() else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    for source in (payload, payload.get("audit_summary")):
        if not isinstance(source, dict):
            continue
        for key in ("domain", "own_domain", "website_domain", "website_url", "site_url", "url"):
            domain = _clean_domain(str(source.get(key) or ""))
            if domain:
                return domain
    return ""


def normalize_keyword_records(records: list[dict[str, Any]], primary_keyword: str = "") -> list[dict[str, Any]]:
    """Perform input hygiene only; relevance and intent decisions belong to the agent."""
    normalized: dict[str, dict[str, Any]] = {}
    for raw in records:
        phrase = clean_phrase(str(raw.get("phrase") or ""))
        if not phrase or not is_publishable_keyword(phrase, min_words=1):
            continue
        current = normalized.get(phrase)
        candidate = {
            "phrase": phrase,
            "type": str(raw.get("type") or raw.get("keyword_type") or "long-tail"),
            "search_volume": _integer_or_none(raw.get("search_volume")),
            "difficulty": _float_or_none(raw.get("difficulty")),
            "frequency": max(1, _integer_or_none(raw.get("frequency")) or 1),
            "source_domains": [
                str(value).strip() for value in raw.get("source_domains") or [] if str(value).strip()
            ],
        }
        if current is None or _metric_score(candidate) > _metric_score(current):
            normalized[phrase] = candidate

    primary = clean_phrase(primary_keyword)
    if primary and primary not in normalized:
        normalized[primary] = {
            "phrase": primary,
            "type": "primary",
            "search_volume": None,
            "difficulty": None,
            "frequency": 1,
            "source_domains": [],
        }
    return list(normalized.values())


def _integer_or_none(value: Any) -> int | None:
    try:
        return int(float(value)) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        return round(float(value), 2) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


def _metric_score(item: dict[str, Any]) -> tuple[int, int, float]:
    return (
        1 if item.get("search_volume") is not None else 0,
        int(item.get("search_volume") or 0),
        -float(item.get("difficulty") if item.get("difficulty") is not None else 101),
    )


def _slug(value: str) -> str:
    return "/" + re.sub(r"[^a-z0-9]+", "-", clean_phrase(value)).strip("-") + "/"


def _minimum_authority_pages(usable_keyword_count: int) -> int:
    if usable_keyword_count < 8:
        return 1
    if usable_keyword_count < 25:
        return 3
    return min(16, max(6, math.ceil(math.sqrt(usable_keyword_count))))


def _tool_volume_threshold(records: list[dict[str, Any]]) -> int:
    volumes = sorted(
        int(item["search_volume"])
        for item in records
        if item.get("search_volume") is not None and int(item["search_volume"]) > 0
    )
    if not volumes:
        return 250
    percentile_index = min(len(volumes) - 1, math.floor((len(volumes) - 1) * 0.65))
    return max(250, volumes[percentile_index])


def _has_tool_intent(keyword: str) -> bool:
    value = clean_phrase(keyword)
    if re.search(
        r"\b(terms(?: and conditions)?|privacy(?: policy)?|disclaimer|about us|contact us|cookie policy|"
        r"refund policy|editorial policy|accessibility|legal|support|faq|guide|tutorial|meaning|"
        r"interpretation|review|comparison|alternatives|article|history|accuracy|errors|mistakes|troubleshooting|how to)\b|\bvs\b",
        value,
    ):
        return False
    return bool(re.search(
        r"\b(calculator|generator|checker|converter|builder|maker|simulator|estimator|planner|tool|software)\b",
        value,
    ))


def _has_strong_tool_intent(keyword: str) -> bool:
    return _has_tool_intent(keyword) and bool(re.search(
        r"\b(calculator|generator|checker|converter|simulator|estimator)\b",
        clean_phrase(keyword),
    ))


def _looks_incomplete_keyword(keyword: str) -> bool:
    return looks_incomplete_search_query(keyword)


CAUSE_INTENT_TERMS = {
    "cause", "causes", "caused", "reason", "reasons", "why", "happen", "happens", "happening",
}


def _causal_topic_terms(keyword: str) -> set[str]:
    ignored = CAUSE_INTENT_TERMS | {
        "a", "an", "are", "does", "do", "for", "is", "it", "of", "the", "to", "what",
    }
    terms = []
    for term in clean_phrase(keyword).split():
        if term in ignored:
            continue
        if term.endswith("s") and len(term) > 3 and not term.endswith("ss"):
            term = term[:-1]
        terms.append(term)
    return set(terms)


def _causal_queries_overlap(left_keyword: str, right_keyword: str) -> bool:
    left_value = clean_phrase(left_keyword)
    right_value = clean_phrase(right_keyword)
    if not (
        set(left_value.split()) & CAUSE_INTENT_TERMS
        and set(right_value.split()) & CAUSE_INTENT_TERMS
    ):
        return False
    left_terms = _causal_topic_terms(left_value)
    right_terms = _causal_topic_terms(right_value)
    if not left_terms or not right_terms:
        return False
    matched_left = {
        left
        for left in left_terms
        if any(left == right or SequenceMatcher(None, left, right).ratio() >= 0.72 for right in right_terms)
    }
    similarity = len(matched_left) / max(len(left_terms), len(right_terms))
    return similarity >= 0.6


def _mechanical_causal_conflicts(plan: dict[str, Any]) -> list[dict[str, str]]:
    pages = [plan["master_hub"], *plan["spokes"]]
    causal_pages = []
    for page in pages:
        target = page["target_keyword"]
        if not (set(target.split()) & CAUSE_INTENT_TERMS):
            continue
        page["intent_class"] = "causal_explanation"
        causal_pages.append((page, _causal_topic_terms(target)))
    conflicts: list[dict[str, str]] = []
    for index, (left, left_terms) in enumerate(causal_pages):
        for right, right_terms in causal_pages[index + 1:]:
            if not _causal_queries_overlap(left["target_keyword"], right["target_keyword"]):
                continue
            conflicts.append({
                "page_a": left["target_keyword"],
                "page_b": right["target_keyword"],
                "reason": "Causes, reasons, and why-it-happens queries share one causal-explanation intent.",
                "resolution": "Merge them into one comprehensive causes page.",
            })
    return conflicts


PRIMARY_INTENT_TERMS = {
    "review", "reviews", "calculator", "checker", "generator", "tool", "software",
    "maker", "builder", "converter", "planner", "simulator", "estimator",
    "guide", "online", "free", "best", "official", "website", "site", "app",
}

THIRD_PARTY_PLATFORM_TERMS = {
    "amazon", "ebay", "facebook", "instagram", "linkedin", "pinterest", "quora",
    "reddit", "redit", "tiktok", "trustpilot", "twitter", "walmart", "youtube",
}


def _is_direct_comparison(keyword: str) -> bool:
    return bool(re.search(
        r"\b(vs|versus|compare|comparison|alternative|alternatives)\b",
        clean_phrase(keyword),
    ))


def _contains_third_party_platform(keyword: str) -> bool:
    terms = set(clean_phrase(keyword).split())
    return bool(terms & THIRD_PARTY_PLATFORM_TERMS) and not _is_direct_comparison(keyword)


def _has_unrelated_leading_brand(keyword: str, primary_keyword: str) -> bool:
    if _is_direct_comparison(keyword):
        return False
    terms = clean_phrase(keyword).split()
    core = _primary_core_terms(primary_keyword)
    # This heuristic identifies prefixed brands for product/review EMDs.
    # On generic topics it falsely treats instructional verbs as brand names
    # (for example, "how to calculate lunar age").
    primary_terms = set(clean_phrase(primary_keyword).split())
    protected_product = bool(primary_terms & {"review", "reviews"}) or any(
        any(char.isdigit() for char in term) for term in core
    )
    if not protected_product or len(core) < 2:
        return False
    for index in range(len(terms) - 1):
        if terms[index:index + 2] != core[:2] or index < 2:
            continue
        allowed = {
            "best", "buy", "buying", "can", "consider", "do", "does", "how", "is", "official",
            "on", "order", "recommended", "review", "reviews", "should", "to", "verified", "what",
            "where", "why",
        }
        return not set(terms[:index]) <= allowed
    return False


def _primary_core_terms(primary_keyword: str) -> list[str]:
    return [
        term for term in clean_phrase(primary_keyword).split()
        if term not in PRIMARY_INTENT_TERMS
    ]


def _is_core_entity_relevant(keyword: str, primary_keyword: str) -> bool:
    """Protect the EMD's subject/entity without admitting broad one-word matches."""
    core = _primary_core_terms(primary_keyword)
    phrase = clean_phrase(keyword)
    phrase_terms = set(phrase.split())
    if not core:
        return False
    overlap = sum(term in phrase_terms for term in core)
    if len(core) == 1:
        return overlap == 1
    core_prefix = " ".join(core[:2])
    has_ordered_anchor = bool(re.search(rf"\b{re.escape(core_prefix)}\b", phrase))
    return has_ordered_anchor or overlap == len(core)


def _is_protected_emd_entity(keyword: str, primary_keyword: str) -> bool:
    if _contains_third_party_platform(keyword):
        return False
    primary_terms = set(clean_phrase(primary_keyword).split())
    core = _primary_core_terms(primary_keyword)
    entity_site = bool({"review", "reviews"} & primary_terms) or any(
        any(character.isdigit() for character in term) for term in core
    )
    if not entity_site or not _is_core_entity_relevant(keyword, primary_keyword):
        return False
    phrase = clean_phrase(keyword)
    if phrase == clean_phrase(primary_keyword) or phrase == " ".join(core[:2]):
        return True
    vague_fragments = {
        "available", "before", "bottles", "comes", "customers", "exclusive", "existing",
        "explore", "identical", "know", "product", "recommended", "refill", "solution",
        "sold", "standard", "store", "twice", "verified", "official",
    }
    meaningful = set(phrase.split()) - set(core) - PRIMARY_INTENT_TERMS
    return bool(meaningful - vague_fragments)


def _prompt(records: list[dict[str, Any]], context: str, primary_keyword: str, target_spokes: int | None = None) -> str:
    authority_floor = _minimum_authority_pages(len(records))
    tool_threshold = _tool_volume_threshold(records)
    planning_goal = (
        f"Plan one homepage plus {target_spokes - 5}–{target_spokes + 5} distinct spokes, aiming for {target_spokes}. "
        "This is a planning goal, never a quota. If evidence supports fewer, return fewer and explain the missing coverage. "
        "Editorial proposals are unverified ideas: assess their relevance and distinct intent before accepting them. "
        "Preserve existing owned pages in the architecture, set existing_url to their exact supplied URL, and plan an update. "
        "A brief mention or homepage summary does not exhaust a deeper instructional intent. Do not duplicate a fully served task. "
        "Set existing_url to null for new pages. Never assign multiple pages to one existing URL. "
        "State an exclusive scope and concrete reader outcome for each page, and useful internal links."
        if target_spokes else f"Aim for at least {authority_floor} pages when distinct intents support them."
    )
    return f"""
Act as a senior technical SEO architect whose specialty is hub-and-spoke information architecture.
You own the complete decision. Study the website context and every supplied keyword, then create a
topical-authority architecture that covers the subject deeply without search-intent cannibalization.

WEBSITE CONTEXT
{context or "No additional context was supplied. Infer scope conservatively from the keyword set."}

Any competitor_profile or competitor_exclusions data in this context is exclusion evidence only. Never
turn those competitor brands, domains, products, or navigational searches into this site's target keywords.

PRIMARY TOPIC
{primary_keyword}

KEYWORD INVENTORY (metrics are evidence, never invent replacements)
{json.dumps(records, ensure_ascii=False)}

PLANNING GOAL
{planning_goal}

Rules:
- Evaluate every exact keyword. Do not omit one.
- Give every keyword exactly one disposition: page_target, supporting, or discard.
- Use page_target only when the query deserves its own indexable URL and has a materially distinct
  search goal or SERP expectation.
- Use supporting when the query is useful but should live as an H2, FAQ, entity, feature, or semantic
  variation on one page. assigned_to must be that page's exact target keyword.
- Use discard for irrelevant, broken, unsafe, obsolete, navigational, duplicate-with-no-added-value,
  or unsupported queries. Give a short specific reason. Never discard merely because volume is absent.
- Discard competitor brand names, competitor domains, competitor product names, and navigational searches
  for another company unless the website context explicitly requests competitor-comparison content.
- Discard queries containing a third-party company, app, social network, review platform, or marketplace
  such as Reddit, Trustpilot, Amazon, YouTube, or Facebook. Keep a named brand only when the query is an
  explicit direct-competitor comparison using "vs", "comparison", or "alternative" intent.
- Discard incomplete, clipped, ungrammatical fragments that do not express a recognizable search intent.
- Treat causes, reasons, "why it happens", and equivalent causal questions about the same subject as one
  page intent. They belong as variants or sections on one comprehensive causes spoke, never separate URLs.
- Never create two pages that would compete for the same search intent. Variants with the same user
  goal belong on one page. Similar words with different goals may remain separate pages.
- The requested PRIMARY TOPIC is the exact-match-domain homepage. It is non-negotiable: master_target
  must equal "{primary_keyword}" exactly, it is the only homepage, and it represents the site's core product.
- Build topical authority around that homepage. Create distinct spokes for meaningful subtopics, entities,
  methods, interpretations, use cases, comparisons, accuracy questions, and advanced concepts supported
  by this inventory. A tool page, a manual how-to guide, and an explanatory article have different intent.
- Do not collapse distinct informational needs into the homepage or a few mega-pages.
  Related wording is not sufficient reason to merge pages with different reader outcomes.
- Assign broad variants of the core product to the homepage, but reserve informational and educational
  queries for the most specific spoke that can satisfy them completely.
- A strong standalone calculator, generator, checker, converter, simulator, or estimator query may be a
  tool even at low volume because the SERP intent requires an interactive result. Other possible tool spokes
  require supplied search volume of at least {tool_threshold:,}; otherwise use an article or guide.
- For weaker tool-like terms such as software, maker, builder, planner, or generic tool queries, require
  supplied search volume of at least {tool_threshold:,}. When volume is lower or unknown, make that spoke
  a focused article/guide instead. The EMD master homepage follows its real intent: a
  calculator EMD is a tool, while a reviews, information, or editorial EMD is a content homepage.
- Every page target and every keyword named in an assignment must be copied exactly from the inventory.
- Discard only genuinely unusable or off-topic phrases. Awkward but understandable phrases can support a page.
- Page titles, headings, questions, briefs, and link explanations may be newly written natural language.
- Every spoke links to the master. The master links to every spoke. Add only useful lateral links.

Keep the response compact. Do not write full article outlines. Return only one JSON object with this schema:
{{
  "site_strategy": "concise expert rationale",
  "master_target": "exact inventory keyword",
  "pages": [{{
    "target_keyword": "exact inventory keyword", "search_intent": "specific unique intent",
    "intent_class": "transactional_tool/informational_guide/definition/interpretation/comparison/troubleshooting/reference",
    "spoke_category": "meaningful topical silo", "article_title": "...", "page_type": "article or tool",
    "content_brief": "one or two sentences explaining the page's exclusive scope",
    "existing_url": null, "internal_links": ["exact related page target"]
  }}],
  "keyword_decisions": [
    ["exact keyword", "page_target", "same exact keyword", "title", "short reason"],
    ["exact keyword", "supporting", "exact page target", "h2/faq/entity/feature/variation", "short reason"],
    ["exact keyword", "discard", null, null, "short reason"]
  ],
  "interlinking_strategy": "..."
}}

pages must contain the master and every spoke, once each. keyword_decisions must contain every inventory
keyword once. Use the compact five-value arrays exactly as shown.
"""


def _coerce_object(payload: Any) -> dict[str, Any] | None:
    """Accept common provider wrappers without accepting incomplete fragment lists."""
    value = payload
    for _ in range(4):
        if isinstance(value, dict):
            for key in ("architecture", "result", "output", "data"):
                nested = value.get(key)
                if isinstance(nested, (dict, str)):
                    value = nested
                    break
            else:
                return value
            continue
        if isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict):
            value = value[0]
            continue
        if isinstance(value, str):
            candidate = value.strip()
            if candidate.startswith("```json") and candidate.endswith("```"):
                candidate = candidate[7:-3].strip()
            elif candidate.startswith("```") and candidate.endswith("```"):
                candidate = candidate[3:-3].strip()
            try:
                value = json.loads(candidate)
                continue
            except json.JSONDecodeError:
                return None
        return None
    return value if isinstance(value, dict) else None


def _clean_page(raw: dict[str, Any], metrics: dict[str, dict[str, Any]]) -> dict[str, Any]:
    target = clean_phrase(str(raw.get("target_keyword") or ""))
    metric = metrics.get(target, {})
    sections = []
    for raw_section in raw.get("h2_sections") or []:
        if not isinstance(raw_section, dict):
            continue
        sections.append({
            "h2_heading": str(raw_section.get("h2_heading") or "").strip(),
            "section_definition": str(raw_section.get("section_definition") or "").strip(),
            "targeted_keywords_placed_here": [
                clean_phrase(str(value)) for value in raw_section.get("targeted_keywords_placed_here") or []
            ],
        })
    faqs = []
    for raw_faq in raw.get("faq_schema_questions") or []:
        if not isinstance(raw_faq, dict):
            continue
        faqs.append({
            "question": str(raw_faq.get("question") or "").strip(),
            "targeted_keywords_placed_here": [
                clean_phrase(str(value)) for value in raw_faq.get("targeted_keywords_placed_here") or []
            ],
        })
    page_type = "tool" if str(raw.get("page_type") or "").lower() == "tool" else "article"
    intent_class = str(raw.get("intent_class") or "").strip().lower().replace(" ", "_")
    if not intent_class:
        intent_class = "transactional_tool" if page_type == "tool" else "informational_guide"
    return {
        "spoke_category": str(raw.get("spoke_category") or "Strategic topic").strip(),
        "article_title": str(raw.get("article_title") or target.title()).strip(),
        "target_keyword": target,
        "search_intent": str(raw.get("search_intent") or "").strip(),
        "intent_class": intent_class,
        "ranking_role": str(raw.get("ranking_role") or "supporting_spoke").strip(),
        "search_volume": metric.get("search_volume"),
        "difficulty": metric.get("difficulty"),
        "slug": _slug(target),
        "existing_url": str(raw.get("existing_url") or "").strip() or None,
        "page_type": page_type,
        "word_count_suggestion": max(500, min(6000, _integer_or_none(raw.get("word_count_suggestion")) or 1800)),
        "content_brief": str(raw.get("content_brief") or "").strip(),
        "targeted_keywords": [],
        "tool_functions": [str(value).strip() for value in raw.get("tool_functions") or [] if str(value).strip()],
        "h2_sections": sections,
        "faq_schema_questions": faqs,
        "entity_terms": [clean_phrase(str(value)) for value in raw.get("entity_terms") or []],
        "internal_links": [clean_phrase(str(value)) for value in raw.get("internal_links") or []],
        "writing_instructions": str(raw.get("writing_instructions") or "").strip(),
    }


def _normalize_plan(
    payload: dict[str, Any], records: list[dict[str, Any]], primary_keyword: str = "",
) -> dict[str, Any]:
    metrics = {item["phrase"]: item for item in records}
    if isinstance(payload.get("pages"), list):
        raw_pages = [item for item in payload["pages"] if isinstance(item, dict)]
        master_target = clean_phrase(primary_keyword) or clean_phrase(str(payload.get("master_target") or ""))
        master_raw = next(
            (item for item in raw_pages if clean_phrase(str(item.get("target_keyword") or "")) == master_target),
            raw_pages[0] if raw_pages else {},
        )
        spoke_raw = [item for item in raw_pages if item is not master_raw]
    else:
        master_raw = payload.get("master_hub") or {}
        spoke_raw = payload.get("spokes") or []
    master = _clean_page(master_raw, metrics)
    master["ranking_role"] = "master_hub"
    master["slug"] = "/"
    spokes = [_clean_page(item, metrics) for item in spoke_raw if isinstance(item, dict)]
    assignments = []
    raw_assignments = payload.get("keyword_assignments") or payload.get("keyword_decisions") or []
    for raw in raw_assignments:
        if isinstance(raw, (list, tuple)) and len(raw) >= 5:
            raw = {
                "keyword": raw[0], "disposition": raw[1], "assigned_to": raw[2],
                "placement": raw[3], "reason": raw[4],
            }
        if not isinstance(raw, dict):
            continue
        assignments.append({
            "keyword": clean_phrase(str(raw.get("keyword") or "")),
            "disposition": str(raw.get("disposition") or "").strip().lower(),
            "assigned_to": clean_phrase(str(raw.get("assigned_to") or "")) or None,
            "placement": str(raw.get("placement") or "").strip().lower() or None,
            "reason": str(raw.get("reason") or "").strip(),
        })
    return {
        "site_strategy": str(payload.get("site_strategy") or "").strip(),
        "_planning_thought": str(payload.get("site_strategy") or "").strip(),
        "master_hub": master,
        "spokes": spokes,
        "keyword_assignments": assignments,
        "interlinking_strategy": str(payload.get("interlinking_strategy") or "").strip(),
        "writing_standards": WRITING_STANDARDS,
        "_keyword_metrics": records,
    }


def _infer_intent_class(keyword: str) -> str:
    value = clean_phrase(keyword)
    if re.search(r"\b(review|reviews|testimonial|testimonials)\b", value):
        return "review"
    if re.search(r"\b(vs|versus|compare|comparison|difference)\b", value):
        return "comparison"
    if re.search(r"\b(how|manual|calculate|guide|tutorial)\b", value):
        return "informational_guide"
    if re.search(r"\b(accuracy|accurate|unknown|without|wrong|error|birth time)\b", value):
        return "troubleshooting"
    if re.search(r"\b(meaning|what is|definition)\b", value):
        return "definition"
    if re.search(r"\b(interpret|purpose|direction|expression|reveal)\w*\b", value):
        return "interpretation"
    if "calculator" in value:
        return "transactional_tool"
    return "reference"


def _infer_category(keyword: str) -> str:
    value = clean_phrase(keyword)
    category_rules = (
        (r"\b(ingredient|botanical|oil|extract|formula|formulation)\w*\b", "Ingredients and formulation"),
        (r"\b(side effect|safety|safe|allergic|allergy|sensitive|avoid|burning)\w*\b", "Safety and side effects"),
        (r"\b(price|pricing|buy|buying|order|cost|where to buy|guarantee|refund)\w*\b", "Pricing and purchase"),
        (r"\b(review|reddit|trustpilot|amazon|testimonial|real user|before and after)\w*\b", "Reviews and evidence"),
        (r"\b(vs|versus|compare|comparison|alternative)\w*\b", "Comparisons and alternatives"),
        (r"\b(australia|indonesia|zealand|regional|country|countries)\b|\bnz\b", "Regional availability"),
        (r"\b(how to use|usage|use daily|twice|dose|dosage|apply|application)\w*\b", "Usage and application"),
        (r"\b(benefit|works|protect|receding|bleeding|bad breath|tooth decay|gum)\w*\b", "Benefits and oral-health use cases"),
        (r"\b(transit|return|cycle|period|activation)\w*\b", "Timing and transits"),
        (r"\b(compatib|synastry|relationship)\w*\b", "Relationships and compatibility"),
        (r"\b(sign|zodiac|house|placement|birth chart)\w*\b", "Signs, houses and placements"),
        (r"\b(calculate|manual|accuracy|accurate|birth time|unknown time|method)\w*\b", "Methods and accuracy"),
        (r"\b(karm|past life|soul|vedic|rahu|ketu)\w*\b", "Karmic themes and traditions"),
        (r"\b(meaning|interpret|purpose|definition|expression)\w*\b", "Meanings and interpretation"),
    )
    for pattern, category in category_rules:
        if re.search(pattern, value):
            return category
    return "Foundational guides"


def _is_page_target_candidate(keyword: str, primary_keyword: str) -> bool:
    phrase_terms = clean_phrase(keyword).split()
    core = _primary_core_terms(primary_keyword)
    if len(core) < 2:
        return True
    anchor = core[:2]
    for index in range(len(phrase_terms) - 1):
        if phrase_terms[index:index + 2] != anchor:
            continue
        leading = set(phrase_terms[:index])
        return not leading or leading <= {
            "buy", "buying", "order", "best", "verified", "official", "where", "to",
        }
    return False


def _resolve_inventory_keyword(value: str, candidates: list[str]) -> str | None:
    requested = clean_phrase(value)
    if not requested:
        return None
    if requested in candidates:
        return requested
    requested_terms = set(requested.split())
    best_keyword = ""
    best_score = 0.0
    for keyword in candidates:
        keyword_terms = set(keyword.split())
        overlap = len(requested_terms & keyword_terms)
        if not overlap:
            continue
        union = len(requested_terms | keyword_terms) or 1
        score = (overlap / union) * 0.65 + SequenceMatcher(None, requested, keyword).ratio() * 0.35
        if score > best_score:
            best_keyword, best_score = keyword, score
    return best_keyword if best_score >= 0.58 else None


def _generated_page(target: str, metrics: dict[str, dict[str, Any]]) -> dict[str, Any]:
    intent_class = _infer_intent_class(target)
    page_type = "tool" if intent_class == "transactional_tool" else "article"
    return _clean_page({
        "target_keyword": target,
        "article_title": target.title(),
        "search_intent": f"{intent_class.replace('_', ' ')} for {target}",
        "intent_class": intent_class,
        "spoke_category": _infer_category(target),
        "page_type": page_type,
        "content_brief": f"Satisfy the distinct search intent behind “{target}” without duplicating another page.",
    }, metrics)


def _repair_plan_consistency(
    plan: dict[str, Any], records: list[dict[str, Any]], primary_keyword: str,
) -> dict[str, Any]:
    """Turn structurally inconsistent model output into an exact inventory-backed plan."""
    inventory = [item["phrase"] for item in records]
    inventory_set = set(inventory)
    metrics = {item["phrase"]: item for item in records}
    primary = clean_phrase(primary_keyword) or inventory[0]
    valid_decisions = [
        item for item in plan.get("keyword_assignments") or [] if item.get("keyword") in inventory_set
    ]
    decisions = list({item["keyword"]: item for item in valid_decisions}.values())
    declared_targets = [
        item["keyword"] for item in decisions if item.get("disposition") == "page_target"
    ]
    preferred_candidates = list(dict.fromkeys([primary, *declared_targets, *inventory]))

    repaired_pages: list[dict[str, Any]] = []
    redirects: dict[str, str] = {}
    for page in [plan.get("master_hub") or {}, *(plan.get("spokes") or [])]:
        old_target = clean_phrase(str(page.get("target_keyword") or ""))
        target = _resolve_inventory_keyword(old_target, preferred_candidates)
        if target is None:
            target = _resolve_inventory_keyword(str(page.get("article_title") or ""), preferred_candidates)
        if target is None:
            continue
        if old_target:
            redirects[old_target] = target
        if any(existing["target_keyword"] == target for existing in repaired_pages):
            continue
        page["target_keyword"] = target
        page["slug"] = _slug(target)
        page["search_volume"] = metrics[target].get("search_volume")
        page["difficulty"] = metrics[target].get("difficulty")
        page["intent_class"] = page.get("intent_class") or _infer_intent_class(target)
        if clean_phrase(str(page.get("spoke_category") or "")) in {"", "strategic topic"}:
            page["spoke_category"] = _infer_category(target)
        repaired_pages.append(page)

    by_target = {page["target_keyword"]: page for page in repaired_pages}
    if primary not in by_target:
        by_target[primary] = _generated_page(primary, metrics)
    for target in declared_targets:
        if target not in by_target:
            by_target[target] = _generated_page(target, metrics)

    master = by_target.pop(primary)
    master["target_keyword"] = primary
    master["ranking_role"] = "master_hub"
    master["slug"] = "/"
    master["page_type"] = "tool" if _has_tool_intent(primary) else "article"
    master["intent_class"] = (
        "transactional_tool" if master["page_type"] == "tool" else _infer_intent_class(primary)
    )
    spokes = list(by_target.values())
    for spoke in spokes:
        spoke["ranking_role"] = "supporting_spoke"

    decision_by_keyword = {item["keyword"]: item for item in decisions}
    page_targets = {primary, *(page["target_keyword"] for page in spokes)}
    for target in page_targets:
        decision = decision_by_keyword.get(target)
        if decision is None:
            decision = {
                "keyword": target, "disposition": "page_target", "assigned_to": target,
                "placement": "title", "reason": "Selected as a distinct topical-authority page.",
            }
            decisions.append(decision)
            decision_by_keyword[target] = decision
        else:
            decision.update({"disposition": "page_target", "assigned_to": target, "placement": "title"})
    for keyword in inventory:
        if keyword in decision_by_keyword:
            continue
        if _is_protected_emd_entity(keyword, primary) and not _looks_incomplete_keyword(keyword):
            destination = _resolve_inventory_keyword(keyword, list(page_targets)) or primary
            decision = {
                "keyword": keyword, "disposition": "supporting", "assigned_to": destination,
                "placement": "h2",
                "reason": "Retained because it is explicitly anchored to the site's core EMD entity.",
            }
        else:
            decision = {
                "keyword": keyword, "disposition": "discard", "assigned_to": None,
                "placement": None,
                "reason": "The specialist did not provide a validated topical placement for this keyword.",
            }
        decisions.append(decision)
        decision_by_keyword[keyword] = decision
    for decision in decisions:
        keyword = decision["keyword"]
        if keyword in page_targets:
            continue
        destination = decision.get("assigned_to")
        if destination in redirects:
            destination = redirects[destination]
        if decision.get("disposition") == "page_target":
            decision["disposition"] = "supporting"
        if (
            decision.get("disposition") == "discard"
            and _is_protected_emd_entity(keyword, primary)
            and not _looks_incomplete_keyword(keyword)
        ):
            decision["disposition"] = "supporting"
            decision["placement"] = "h2"
            decision["reason"] = "Retained because it is anchored to the site's core EMD entity."
        if decision.get("disposition") == "supporting" and destination not in page_targets:
            destination = _resolve_inventory_keyword(str(destination or keyword), list(page_targets)) or primary
        if decision.get("disposition") == "supporting":
            decision["assigned_to"] = destination

    seen_intents: set[str] = set()
    for page in [master, *spokes]:
        intent = clean_phrase(str(page.get("search_intent") or ""))
        if not intent or intent in seen_intents:
            intent = f"{page['intent_class'].replace('_', ' ')} for {page['target_keyword']}"
            page["search_intent"] = intent
        seen_intents.add(clean_phrase(intent))

    plan["master_hub"] = master
    plan["spokes"] = spokes
    plan["keyword_assignments"] = decisions
    return plan


def _ensure_topical_authority(
    plan: dict[str, Any], records: list[dict[str, Any]], primary_keyword: str,
    excluded_page_targets: set[str] | None = None,
) -> dict[str, Any]:
    """Promote diverse, relevant supporting terms when the model returns a one-page plan."""
    metrics = {item["phrase"]: item for item in records}
    decisions = plan["keyword_assignments"]
    usable = [item for item in decisions if item.get("disposition") != "discard"]
    minimum_pages = _minimum_authority_pages(len(usable))
    existing_targets = {
        plan["master_hub"]["target_keyword"],
        *(page["target_keyword"] for page in plan["spokes"]),
    }
    excluded_page_targets = excluded_page_targets or set()
    if len(existing_targets) < minimum_pages:
        candidates = [
            item["keyword"] for item in usable
            if item.get("disposition") == "supporting"
            and item["keyword"] not in existing_targets
            and item["keyword"] not in excluded_page_targets
            and _is_core_entity_relevant(item["keyword"], primary_keyword)
            and _is_page_target_candidate(item["keyword"], primary_keyword)
            and not any(
                _causal_queries_overlap(item["keyword"], target)
                for target in existing_targets
            )
        ]
        candidates.sort(key=lambda keyword: (
            int(metrics[keyword].get("search_volume") or 0),
            int(metrics[keyword].get("frequency") or 1),
            len(keyword.split()),
        ), reverse=True)
        selected: list[str] = []
        used_categories = {
            page.get("spoke_category")
            for page in [plan["master_hub"], *plan["spokes"]]
            if page.get("spoke_category")
        }
        for keyword in candidates:
            category = _infer_category(keyword)
            if category not in used_categories:
                selected.append(keyword)
                used_categories.add(category)
            if len(existing_targets) + len(selected) >= minimum_pages:
                break
        for keyword in candidates:
            if keyword in selected:
                continue
            selected.append(keyword)
            if len(existing_targets) + len(selected) >= minimum_pages:
                break
        decision_by_keyword = {item["keyword"]: item for item in decisions}
        for target in selected:
            page = _generated_page(target, metrics)
            page["spoke_category"] = _infer_category(target)
            page["ranking_role"] = "supporting_spoke"
            plan["spokes"].append(page)
            decision_by_keyword[target].update({
                "disposition": "page_target", "assigned_to": target, "placement": "title",
                "reason": "Promoted to provide the topical depth required by this keyword inventory.",
            })
            existing_targets.add(target)

    pages = [plan["master_hub"], *plan["spokes"]]
    target_categories = {
        page["target_keyword"]: page.get("spoke_category") or _infer_category(page["target_keyword"])
        for page in pages
    }
    target_terms = {
        target: set(target.split()) for target in target_categories
    }
    for decision in decisions:
        if decision.get("disposition") != "supporting":
            continue
        keyword = decision["keyword"]
        terms = set(keyword.split())
        category = _infer_category(keyword)
        ranked_targets = sorted(existing_targets, key=lambda target: (
            1 if target_categories[target] == category else 0,
            len(terms & target_terms[target]) / max(1, len(terms | target_terms[target])),
            int(metrics[target].get("search_volume") or 0),
        ), reverse=True)
        decision["assigned_to"] = ranked_targets[0]
    return plan


def _apply_tool_roi_rules(plan: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    """Reserve costly spoke tools for explicit tool queries with enough measured demand."""
    threshold = _tool_volume_threshold(records)
    master = plan["master_hub"]
    master_is_tool = _has_tool_intent(master["target_keyword"])
    master["page_type"] = "tool" if master_is_tool else "article"
    master["intent_class"] = (
        "transactional_tool" if master_is_tool else _infer_intent_class(master["target_keyword"])
    )
    master["tool_economics"] = {
        "qualifies": master_is_tool,
        "reason": (
            "The EMD primary keyword has direct interactive-tool intent."
            if master_is_tool
            else "The EMD primary keyword has content intent, so the homepage is an article/editorial hub."
        ),
        "minimum_volume": threshold,
        "search_volume": master.get("search_volume"),
        "difficulty": master.get("difficulty"),
    }
    for page in plan.get("spokes") or []:
        volume = int(page.get("search_volume") or 0)
        difficulty = float(page.get("difficulty") if page.get("difficulty") is not None else 100)
        explicit_tool_intent = _has_tool_intent(page["target_keyword"])
        strong_tool_intent = _has_strong_tool_intent(page["target_keyword"])
        demand_justifies_effort = volume >= threshold and (
            difficulty <= 65 or volume >= threshold * 3
        )
        qualifies = strong_tool_intent or (explicit_tool_intent and demand_justifies_effort)
        page["page_type"] = "tool" if qualifies else "article"
        if qualifies:
            page["intent_class"] = "transactional_tool"
            if strong_tool_intent:
                reason = "Strong interactive-tool intent justifies a tool even at low or unknown volume."
            else:
                reason = (
                    f"Tool intent with volume {volume:,} meets the {threshold:,} demand threshold"
                    + (" despite high difficulty." if difficulty > 65 else ".")
                )
        else:
            page["tool_functions"] = []
            if not explicit_tool_intent:
                reason = "The query does not require an interactive result, so an article is the right format."
            elif not volume:
                reason = "No verified search volume is available to justify building another tool."
            elif volume < threshold:
                reason = f"Volume {volume:,} is below the {threshold:,} tool-effort threshold."
            else:
                reason = (
                    f"Volume {volume:,} does not justify a separate tool at difficulty {difficulty:.0f}; "
                    "use a focused article instead."
                )
        page["tool_economics"] = {
            "qualifies": qualifies,
            "reason": reason,
            "minimum_volume": threshold,
            "search_volume": page.get("search_volume"),
            "difficulty": page.get("difficulty"),
        }
    plan["tool_volume_threshold"] = threshold
    return plan


def validate_architecture(
    plan: dict[str, Any], records: list[dict[str, Any]], required_master_target: str = "",
) -> list[str]:
    inventory = {item["phrase"] for item in records}
    errors: list[str] = []
    master = plan.get("master_hub") or {}
    pages = [master, *(plan.get("spokes") or [])]
    targets = [page.get("target_keyword") for page in pages]
    if not targets or not targets[0]:
        errors.append("one master hub is required")
    required_master = clean_phrase(required_master_target)
    if required_master and targets and targets[0] != required_master:
        errors.append(f'the EMD homepage must target the primary keyword "{required_master}"')
    if master.get("slug") != "/":
        errors.append("the master hub must be the homepage at /")
    if any(target not in inventory for target in targets):
        errors.append("every page target must be an exact supplied keyword")
    if len(targets) != len(set(targets)):
        errors.append("page target keywords must be unique")
    slugs = [page.get("slug") for page in pages]
    if len(slugs) != len(set(slugs)):
        errors.append("page slugs must be unique")
    intents = [clean_phrase(str(page.get("search_intent") or "")) for page in pages]
    if any(not intent for intent in intents):
        errors.append("every page needs an explicit search intent")
    if len(intents) != len(set(intents)):
        errors.append("two pages have the same declared search intent")

    assignments = plan.get("keyword_assignments") or []
    assigned_keywords = [item.get("keyword") for item in assignments]
    missing = sorted(inventory - set(assigned_keywords))
    unknown = sorted(set(assigned_keywords) - inventory)
    duplicates = sorted({value for value in assigned_keywords if assigned_keywords.count(value) > 1})
    if missing:
        errors.append(f"keywords without a decision: {missing[:25]}")
    if unknown:
        errors.append(f"invented keywords in decisions: {unknown[:25]}")
    if duplicates:
        errors.append(f"keywords with multiple decisions: {duplicates[:25]}")
    page_targets = set(targets)
    for item in assignments:
        disposition = item.get("disposition")
        keyword = item.get("keyword")
        assigned_to = item.get("assigned_to")
        if disposition not in {"page_target", "supporting", "discard"}:
            errors.append(f"invalid disposition for {keyword}")
        elif disposition == "page_target" and (keyword not in page_targets or assigned_to != keyword):
            errors.append(f"page target decision is inconsistent for {keyword}")
        elif disposition == "supporting" and assigned_to not in page_targets:
            errors.append(f"supporting keyword {keyword} has no valid destination")
        elif disposition == "discard" and assigned_to:
            errors.append(f"discarded keyword {keyword} cannot have a destination")
        if not item.get("reason"):
            errors.append(f"keyword decision needs a reason: {keyword}")
    if page_targets != {item.get("keyword") for item in assignments if item.get("disposition") == "page_target"}:
        errors.append("page targets and page_target decisions do not match")

    usable = [item for item in assignments if item.get("disposition") != "discard"]
    minimum_pages = _minimum_authority_pages(len(usable))
    if not plan.get("_authority_target") and len(pages) < minimum_pages:
        errors.append(
            f"topical authority is too shallow: {len(usable)} usable keywords require at least "
            f"{minimum_pages} distinct intent pages, but only {len(pages)} were created"
        )
    if len(pages) >= 6:
        categories = {
            clean_phrase(str(page.get("spoke_category") or ""))
            for page in plan.get("spokes") or []
        }
        categories.discard("")
        categories.discard("strategic topic")
        if len(categories) < 3:
            errors.append("topical authority needs at least three meaningful spoke categories")
    if not plan.get("_authority_target") and len(usable) >= 30:
        assignment_counts = {
            target: sum(1 for item in usable if item.get("assigned_to") == target)
            for target in page_targets
        }
        overloaded_target, overloaded_count = max(assignment_counts.items(), key=lambda item: item[1])
        maximum_share = math.ceil(len(usable) * 0.45)
        if overloaded_count > maximum_share:
            errors.append(
                f'page "{overloaded_target}" absorbs {overloaded_count} of {len(usable)} usable keywords; '
                f"split distinct informational intents into topical spokes (maximum {maximum_share})"
            )
    return list(dict.fromkeys(errors))


async def _audit_intent_cannibalization(
    plan: dict[str, Any], context: str,
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[str]]:
    """Use a separate review pass to catch semantic overlap hidden by different wording."""
    pages = [plan["master_hub"], *plan["spokes"]]
    review_input = [{
        "target_keyword": page["target_keyword"],
        "search_intent": page["search_intent"],
        "intent_class": page["intent_class"],
        "article_title": page["article_title"],
        "page_type": page["page_type"],
        "content_brief": page["content_brief"],
    } for page in pages]
    keyword_placements = [{
        "keyword": item["keyword"],
        "assigned_to": item.get("assigned_to"),
        "disposition": item.get("disposition"),
    } for item in plan.get("keyword_assignments") or [] if item.get("disposition") != "discard"]
    audit = await _achat_json(
        system_prompt=(
            "You are the final SEO cannibalization reviewer. Compare page intents as user goals and "
            "likely SERP expectations, even when labels use different words. Return only JSON."
        ),
        user_prompt=f"""
Website context:
{context or "No additional context supplied."}

Proposed indexable pages:
{json.dumps(review_input, ensure_ascii=False)}

Retained keyword placements:
{json.dumps(keyword_placements, ensure_ascii=False)}

Find only pairs that would satisfy the same user goal with the same result type. Do not flag pages merely
because they discuss the same entity. A calculator/tool, a manual calculation guide, a definition, an
interpretation, and a comparison serve different intents and should coexist as topical-authority spokes.
Likewise, entity-specific pages may coexist when each gives a complete answer about a distinct entity.
Causes, reasons, "why it happens", and equivalent causal questions about the same subject are the same
intent and must be reported as a conflict if proposed as separate pages.
Also reject retained keywords that are clearly unrelated, broken, competitor-branded, another company's
product/domain, or navigational searches for another site. A keyword containing relevant topic words is
still irrelevant when its real intent is reaching a competitor. Do not reject useful non-branded subtopics.
Reject third-party company, app, platform, social-network, review-site, and marketplace modifiers such as
Reddit, Trustpilot, Amazon, YouTube, or Facebook. A named company may remain only when the keyword expresses
direct competitor-comparison intent with "vs", "comparison", or "alternative" wording.
Reject clipped, nonsensical, or incomplete phrases that do not express a recognizable search intent.
The master target is the site's protected EMD subject. Do not reject keywords anchored to that core entity
merely because competitor source pages also discuss or sell the same product. Product reviews, ingredients,
side effects, buying intent, source-specific reviews, and explicit "core product vs competitor" comparisons
remain relevant when they genuinely concern the protected EMD subject.
Return:
{{"passed": true, "conflicts": [], "rejections": []}}
or
{{"passed": false, "conflicts": [{{"page_a": "exact target", "page_b": "exact target", "reason": "...", "resolution": "merge or clarify"}}], "rejections": [{{"keyword": "exact retained keyword", "reason": "specific reason"}}]}}
""",
        temperature=0,
        max_tokens=3000,
    )
    audit = _coerce_object(audit)
    if audit is None or not isinstance(audit.get("conflicts"), list):
        return [], [], ["the semantic cannibalization review returned an invalid result"]
    retained = {item["keyword"] for item in keyword_placements}
    primary_target = plan["master_hub"]["target_keyword"]
    def should_honor_rejection(item: dict[str, Any]) -> bool:
        keyword = clean_phrase(str(item.get("keyword") or ""))
        if not _is_protected_emd_entity(keyword, primary_target):
            return True
        reason = clean_phrase(str(item.get("reason") or ""))
        third_party_reason = bool(set(reason.split()) & {
            "app", "brand", "company", "marketplace", "navigational", "platform", "social",
        })
        return third_party_reason and not _is_direct_comparison(keyword)

    rejections = [
        {
            "keyword": clean_phrase(str(item.get("keyword") or "")),
            "reason": str(item.get("reason") or "Rejected by the relevance review.").strip(),
        }
        for item in audit.get("rejections") or []
        if (
            isinstance(item, dict)
            and clean_phrase(str(item.get("keyword") or "")) in retained
            and should_honor_rejection(item)
        )
    ]
    raw_conflicts = [item for item in audit["conflicts"] if isinstance(item, dict)]
    by_target = {page["target_keyword"]: page for page in pages}
    conflicts = []
    for item in raw_conflicts:
        left = by_target.get(clean_phrase(str(item.get("page_a") or "")))
        right = by_target.get(clean_phrase(str(item.get("page_b") or "")))
        if left and right and (
            left["page_type"] != right["page_type"]
            or left["intent_class"] != right["intent_class"]
        ):
            logger.info(
                "Ignoring cross-intent cannibalization suggestion: %s vs %s",
                left["target_keyword"], right["target_keyword"],
            )
            continue
        conflicts.append(item)
    if audit.get("passed") is True and not conflicts:
        return [], rejections, []
    if raw_conflicts and not conflicts:
        return [], rejections, []
    if not conflicts:
        if rejections:
            return [], rejections, []
        return [], [], ["the semantic cannibalization review did not approve the architecture"]
    errors = [
        "intent conflict: " + str(item.get("page_a") or "unknown") + " vs "
        + str(item.get("page_b") or "unknown") + " — " + str(item.get("reason") or "overlapping intent")
        for item in conflicts
    ]
    return conflicts, rejections, errors or ["the semantic cannibalization review found an unspecified conflict"]


def _apply_relevance_rejections(
    plan: dict[str, Any], rejections: list[dict[str, str]],
) -> list[str]:
    master_target = plan["master_hub"]["target_keyword"]
    reasons = {
        item["keyword"]: item["reason"]
        for item in rejections
        if item.get("keyword") and item["keyword"] != master_target
    }
    if not reasons:
        return []
    rejected_targets = {
        item["keyword"] for item in plan["keyword_assignments"]
        if item["keyword"] in reasons and item.get("disposition") == "page_target"
    }
    plan["spokes"] = [
        page for page in plan["spokes"] if page["target_keyword"] not in rejected_targets
    ]
    remaining_targets = [master_target, *(page["target_keyword"] for page in plan["spokes"])]
    for decision in plan["keyword_assignments"]:
        keyword = decision["keyword"]
        if keyword in reasons:
            decision.update({
                "disposition": "discard", "assigned_to": None, "placement": None,
                "reason": reasons[keyword],
            })
        elif decision.get("assigned_to") in rejected_targets:
            decision["assigned_to"] = (
                _resolve_inventory_keyword(keyword, remaining_targets) or master_target
            )
            decision["reason"] = "Reassigned after an irrelevant destination page was removed."
    return sorted(reasons)


def _deterministic_third_party_rejections(
    plan: dict[str, Any], primary_keyword: str,
) -> list[dict[str, str]]:
    return [
        {
            "keyword": item["keyword"],
            "reason": (
                "Contains a third-party platform or marketplace name without direct competitor-comparison intent."
                if _contains_third_party_platform(item["keyword"])
                else "Contains an unrelated competitor/company/app name before the protected EMD entity."
            ),
        }
        for item in plan.get("keyword_assignments") or []
        if item.get("disposition") != "discard" and (
            _contains_third_party_platform(item["keyword"])
            or _has_unrelated_leading_brand(item["keyword"], primary_keyword)
        )
    ]


def _deterministic_quality_rejections(plan: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "keyword": item["keyword"],
            "reason": "Incomplete or clipped phrase without a complete, recognizable search intent.",
        }
        for item in plan.get("keyword_assignments") or []
        if item.get("disposition") != "discard" and _looks_incomplete_keyword(item["keyword"])
    ]


def _source_domain_brand_rejections(
    plan: dict[str, Any], records: list[dict[str, Any]], primary_keyword: str,
) -> list[dict[str, str]]:
    record_by_keyword = {item["phrase"]: item for item in records}
    core_compact = "".join(_primary_core_terms(primary_keyword))
    hosted_suffixes = {"framer.ai", "webflow.io", "wordpress.com", "godaddysites.com"}
    rejections: list[dict[str, str]] = []
    for decision in plan.get("keyword_assignments") or []:
        keyword = decision["keyword"]
        if decision.get("disposition") == "discard" or _is_direct_comparison(keyword):
            continue
        phrase_compact = re.sub(r"[^a-z0-9]+", "", keyword.lower())
        for raw_domain in record_by_keyword.get(keyword, {}).get("source_domains") or []:
            domain = _clean_domain(raw_domain)
            if not domain:
                continue
            labels = domain.split(".")
            if domain in hosted_suffixes or len(labels) < 2:
                continue
            if any(domain.endswith(f".{suffix}") for suffix in hosted_suffixes):
                brand_label = labels[0]
            elif domain.endswith(".com.au") and len(labels) >= 3:
                brand_label = labels[-3]
            else:
                brand_label = labels[-2]
            brand_compact = re.sub(r"[^a-z0-9]+", "", brand_label)
            if len(brand_compact) < 4:
                continue
            mentions_source_brand = brand_compact in phrase_compact or (
                len(phrase_compact) >= 5 and phrase_compact in brand_compact
            )
            source_is_core_entity = bool(core_compact) and core_compact in brand_compact
            if mentions_source_brand and not source_is_core_entity:
                rejections.append({
                    "keyword": keyword,
                    "reason": f'Contains the unrelated company/app name from source domain "{domain}".',
                })
                break
    return rejections


def _merge_intent_conflicts(
    plan: dict[str, Any], conflicts: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    """Consolidate reviewer-confirmed conflicts instead of failing the whole architecture."""
    pages = [plan["master_hub"], *plan["spokes"]]
    by_target = {page["target_keyword"]: page for page in pages}
    master_target = plan["master_hub"]["target_keyword"]
    redirects: dict[str, str] = {}
    merge_notes: list[str] = []

    def final_target(target: str) -> str:
        seen: set[str] = set()
        while target in redirects and target not in seen:
            seen.add(target)
            target = redirects[target]
        return target

    def strength(target: str) -> tuple[int, int, float]:
        page = by_target[target]
        return (
            1 if target == master_target else 0,
            int(page.get("search_volume") or 0),
            -float(page.get("difficulty") if page.get("difficulty") is not None else 101),
        )

    for conflict in conflicts:
        left = final_target(clean_phrase(str(conflict.get("page_a") or "")))
        right = final_target(clean_phrase(str(conflict.get("page_b") or "")))
        if not left or not right or left == right or left not in by_target or right not in by_target:
            continue
        if (
            by_target[left]["page_type"] != by_target[right]["page_type"]
            or by_target[left]["intent_class"] != by_target[right]["intent_class"]
        ):
            continue
        winner, loser = (left, right) if strength(left) >= strength(right) else (right, left)
        redirects[loser] = winner
        merge_notes.append(
            f'Merged "{loser}" into "{winner}": '
            + str(conflict.get("reason") or "overlapping search intent")
        )

    if not redirects:
        return plan, []
    for loser in list(redirects):
        redirects[loser] = final_target(redirects[loser])
    plan["spokes"] = [
        page for page in plan["spokes"] if page["target_keyword"] not in redirects
    ]
    for decision in plan["keyword_assignments"]:
        keyword = decision["keyword"]
        destination = decision.get("assigned_to")
        if destination in redirects:
            decision["assigned_to"] = redirects[destination]
        if keyword in redirects and decision["disposition"] == "page_target":
            decision["disposition"] = "supporting"
            decision["assigned_to"] = redirects[keyword]
            decision["placement"] = "h2"
            decision["reason"] = "Consolidated into the stronger page after semantic cannibalization review."
    plan["site_strategy"] = " ".join(
        value for value in [plan.get("site_strategy", ""), *merge_notes] if value
    )
    plan["_planning_thought"] = plan["site_strategy"]
    return plan, merge_notes


def _apply_assignments(plan: dict[str, Any]) -> dict[str, Any]:
    master = plan["master_hub"]
    pages = [master, *plan["spokes"]]
    by_target = {page["target_keyword"]: page for page in pages}
    discarded = []
    for page in pages:
        page["targeted_keywords"] = []
        page["entity_terms"] = []
        for section in page["h2_sections"]:
            section["targeted_keywords_placed_here"] = []
        for faq in page["faq_schema_questions"]:
            faq["targeted_keywords_placed_here"] = []
    for decision in plan["keyword_assignments"]:
        if decision["disposition"] == "discard":
            discarded.append({"keyword": decision["keyword"], "reason": decision["reason"]})
        elif decision["disposition"] == "supporting":
            destination = by_target[decision["assigned_to"]]
            keyword = decision["keyword"]
            destination["targeted_keywords"].append(keyword)
            placement = decision.get("placement") or ""
            if "faq" in placement and destination["faq_schema_questions"]:
                destination["faq_schema_questions"][0]["targeted_keywords_placed_here"].append(keyword)
            elif "entity" in placement:
                destination["entity_terms"].append(keyword)
            elif destination["h2_sections"]:
                destination["h2_sections"][0]["targeted_keywords_placed_here"].append(keyword)
    for page in pages:
        page["targeted_keywords"] = list(dict.fromkeys(page["targeted_keywords"]))
        page["internal_links"] = [value for value in dict.fromkeys(page["internal_links"]) if value in by_target and value != page["target_keyword"]]

    master_target = master["target_keyword"]
    spoke_targets = [page["target_keyword"] for page in plan["spokes"]]
    master["internal_links"] = list(dict.fromkeys([*master["internal_links"], *spoke_targets]))
    for spoke in plan["spokes"]:
        spoke["internal_links"] = list(dict.fromkeys([master_target, *spoke["internal_links"]]))

    layers: dict[str, list[str]] = {}
    for spoke in plan["spokes"]:
        category = spoke["spoke_category"] or "Strategic topics"
        include = spoke["targeted_keywords"]
        label = f"{spoke['article_title']} (Target Keyword: {spoke['target_keyword']})"
        if include:
            label += f" [Include: {', '.join(include)}]"
        layers.setdefault(category, []).append(label)
    plan["hubs"] = [{
        "hub_title": f"MASTER HUB: {plan.get('site_domain') or master_target}",
        "target_keyword": master_target,
        "h2_keywords": master["targeted_keywords"],
        "layers": layers,
        "sub_silos": [],
    }]
    plan["discarded_keywords"] = discarded
    plan["filtered_irrelevant_keywords"] = [item["keyword"] for item in discarded]
    plan["total_relevant_keywords_covered"] = sum(
        1 for item in plan["keyword_assignments"] if item["disposition"] != "discard"
    )
    plan["_deduplication_check"] = {
        "unique_target_keywords": "Checked",
        "unique_titles": "Checked",
        "unique_slugs": "Checked",
        "semantic_intents": (
            "Checked by specialist agent"
            if plan.get("_semantic_audit_status") == "passed"
            else "Structural intent safeguards passed"
        ),
        "duplicates_removed": sum(
            1 for item in plan["keyword_assignments"]
            if item["disposition"] == "supporting" and "duplicate" in item["reason"].lower()
        ),
    }
    return plan


async def build_site_architecture(
    records: list[dict[str, Any]],
    *,
    context: str = "",
    primary_keyword: str = "",
    site_domain: str = "",
    target_spokes: int | None = None,
) -> dict[str, Any]:
    normalized = normalize_keyword_records(records, primary_keyword)
    if not normalized:
        raise ArchitectureAgentError("No usable keyword text was supplied.")
    if not is_ai_configured():
        raise ArchitectureAgentError("The SEO architecture agent is unavailable because no AI provider is configured.")

    main = clean_phrase(primary_keyword) or normalized[0]["phrase"]
    discovery_status = "not_requested"
    if target_spokes is not None:
        if not 10 <= target_spokes <= 50:
            raise ArchitectureAgentError("The spoke target must be between 10 and 50.")
        from nlp.authority import expand_inventory
        normalized, discovery_status = await expand_inventory(normalized, context, main, target_spokes, _achat_json)
    prompt = _prompt(normalized, context, main, target_spokes)
    last_errors: list[str] = []
    for attempt in range(3):
        try:
            payload = await _achat_json(
                system_prompt=(
                    "You are a meticulous senior SEO information architect. Account for every supplied "
                    "keyword, prevent intent cannibalization, and return only the requested JSON."
                ),
                user_prompt=prompt,
                temperature=0.15,
                max_tokens=16000,
            )
            payload = _coerce_object(payload)
            if payload is None:
                raise ValueError(
                    "the provider response was incomplete or malformed JSON; retrying with the compact schema"
                )
            plan = _normalize_plan(payload, normalized, main)
            plan = _repair_plan_consistency(plan, normalized, main)
            if target_spokes:
                plan["_authority_target"] = target_spokes
            deterministic_rejections = [
                *_deterministic_third_party_rejections(plan, main),
                *_deterministic_quality_rejections(plan),
                *_source_domain_brand_rejections(plan, normalized, main),
            ]
            _apply_relevance_rejections(plan, deterministic_rejections)
            if not target_spokes:
                plan = _ensure_topical_authority(plan, normalized, main)
            plan = _apply_tool_roi_rules(plan, normalized)
            causal_conflicts = _mechanical_causal_conflicts(plan)
            if causal_conflicts:
                targets_before_merge = {
                    plan["master_hub"]["target_keyword"],
                    *(page["target_keyword"] for page in plan["spokes"]),
                }
                plan, _causal_merge_notes = _merge_intent_conflicts(plan, causal_conflicts)
                targets_after_merge = {
                    plan["master_hub"]["target_keyword"],
                    *(page["target_keyword"] for page in plan["spokes"]),
                }
                if not target_spokes:
                    plan = _ensure_topical_authority(
                        plan,
                        normalized,
                        main,
                        excluded_page_targets=targets_before_merge - targets_after_merge,
                    )
                plan = _apply_tool_roi_rules(plan, normalized)
            last_errors = validate_architecture(plan, normalized, main)
            if not last_errors:
                review_limit = min(5, len(plan["spokes"]) + 1)
                for _review in range(review_limit):
                    try:
                        conflicts, rejections, audit_errors = await _audit_intent_cannibalization(plan, context)
                    except Exception as exc:
                        conflicts = []
                        rejections = []
                        audit_errors = [str(exc) or type(exc).__name__]
                    if rejections:
                        removed_keywords = _apply_relevance_rejections(plan, rejections)
                        if removed_keywords:
                            logger.info(
                                "Relevance review discarded %s retained keywords", len(removed_keywords),
                            )
                            last_errors = validate_architecture(plan, normalized, main)
                            if last_errors:
                                break
                    if audit_errors and not conflicts:
                        logger.warning(
                            "Semantic cannibalization review unavailable; keeping the structurally "
                            "validated architecture: %s", "; ".join(audit_errors),
                        )
                        plan["_semantic_audit_status"] = "unavailable"
                        last_errors = []
                        break
                    last_errors = audit_errors
                    if not conflicts:
                        plan["_semantic_audit_status"] = "passed"
                        break
                    plan, merge_notes = _merge_intent_conflicts(plan, conflicts)
                    if not merge_notes:
                        logger.warning("Ignoring an audit conflict that did not reference valid plan pages")
                        plan["_semantic_audit_status"] = "invalid_conflict_ignored"
                        last_errors = []
                        break
                    last_errors = validate_architecture(plan, normalized, main)
                    if last_errors:
                        break
            if not last_errors:
                plan["site_domain"] = _clean_domain(site_domain) or _domain_from_context(context)
                if target_spokes:
                    from nlp.authority import finish_authority_plan
                    plan = finish_authority_plan(plan, normalized, context, target_spokes, discovery_status)
                    final_errors = validate_architecture(plan, normalized, main)
                    if final_errors:
                        raise ValueError("; ".join(final_errors))
                    if (attempt == 0 and plan["authority_coverage"]["status"] == "needs_research"
                            and len(normalized) >= target_spokes):
                        prompt += (
                            f"\nThe first map had only {len(plan['spokes'])} spokes. Review whether distinct "
                            "instructional, comparison, reference or tool intents were overlooked. "
                            "Return a complete revised map; keep fewer pages if the remaining inventory "
                            "does not justify more. Do not split same-intent variants to fill the target."
                        )
                        continue
                return _apply_assignments(plan)
            logger.warning("SEO architecture agent validation failed: %s", "; ".join(last_errors))
        except Exception as exc:
            last_errors = [str(exc) or type(exc).__name__]
            logger.warning("SEO architecture agent attempt %s failed: %s", attempt + 1, last_errors[0])
        prompt += (
            "\n\nThe previous architecture was rejected by deterministic validation. "
            f"Correct every issue and return the full JSON again: {json.dumps(last_errors)}"
        )
    raise ArchitectureAgentError(
        "The SEO architecture agent could not produce a complete cannibalization-safe plan: "
        + "; ".join(last_errors[:5])
    )


def usable_keywords(plan: dict[str, Any]) -> list[str]:
    return [
        item["keyword"] for item in plan.get("keyword_assignments") or []
        if item.get("disposition") != "discard"
    ]
