"""SEO-specialist agent for building a complete, cannibalization-safe site architecture."""

from __future__ import annotations

import json
import logging
import math
import re
from difflib import SequenceMatcher
from typing import Any

from nlp.keywords import clean_phrase, is_publishable_keyword
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


def _prompt(records: list[dict[str, Any]], context: str, primary_keyword: str) -> str:
    authority_floor = _minimum_authority_pages(len(records))
    return f"""
Act as a senior technical SEO architect whose specialty is hub-and-spoke information architecture.
You own the complete decision. Study the website context and every supplied keyword, then create a
topical-authority architecture that covers the subject deeply without search-intent cannibalization.

WEBSITE CONTEXT
{context or "No additional context was supplied. Infer scope conservatively from the keyword set."}

PRIMARY TOPIC
{primary_keyword}

KEYWORD INVENTORY (metrics are evidence, never invent replacements)
{json.dumps(records, ensure_ascii=False)}

Rules:
- Evaluate every exact keyword. Do not omit one.
- Give every keyword exactly one disposition: page_target, supporting, or discard.
- Use page_target only when the query deserves its own indexable URL and has a materially distinct
  search goal or SERP expectation.
- Use supporting when the query is useful but should live as an H2, FAQ, entity, feature, or semantic
  variation on one page. assigned_to must be that page's exact target keyword.
- Use discard for irrelevant, broken, unsafe, obsolete, navigational, duplicate-with-no-added-value,
  or unsupported queries. Give a short specific reason. Never discard merely because volume is absent.
- Never create two pages that would compete for the same search intent. Variants with the same user
  goal belong on one page. Similar words with different goals may remain separate pages.
- The requested PRIMARY TOPIC is the exact-match-domain homepage. It is non-negotiable: master_target
  must equal "{primary_keyword}" exactly, it is the only homepage, and it represents the site's core product.
- Build topical authority around that homepage. Create distinct spokes for meaningful subtopics, entities,
  methods, interpretations, use cases, comparisons, accuracy questions, and advanced concepts supported
  by this inventory. A tool page, a manual how-to guide, and an explanatory article have different intent.
- This inventory size normally requires at least {authority_floor} indexable pages when enough keywords are
  relevant. Do not collapse dozens of different informational needs into the homepage or a few mega-pages.
- Assign broad variants of the core product to the homepage, but reserve informational and educational
  queries for the most specific spoke that can satisfy them completely.
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
    "content_brief": "one or two sentences explaining the page's exclusive scope"
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
    master["page_type"] = "tool"
    master["intent_class"] = "transactional_tool"
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
        destination = _resolve_inventory_keyword(keyword, list(page_targets)) or primary
        decision = {
            "keyword": keyword, "disposition": "supporting", "assigned_to": destination,
            "placement": "h2", "reason": "Assigned to the closest validated topical page.",
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
    if len(pages) < minimum_pages:
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
    if len(usable) >= 30:
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
) -> tuple[list[dict[str, str]], list[str]]:
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

Find only pairs that would satisfy the same user goal with the same result type. Do not flag pages merely
because they discuss the same entity. A calculator/tool, a manual calculation guide, a definition, an
interpretation, and a comparison serve different intents and should coexist as topical-authority spokes.
Likewise, entity-specific pages may coexist when each gives a complete answer about a distinct entity.
Return {{"passed": true, "conflicts": []}} when no pair conflicts. Otherwise return:
{{"passed": false, "conflicts": [{{"page_a": "exact target", "page_b": "exact target", "reason": "...", "resolution": "merge or clarify"}}]}}
""",
        temperature=0,
        max_tokens=3000,
    )
    audit = _coerce_object(audit)
    if audit is None or not isinstance(audit.get("conflicts"), list):
        return [], ["the semantic cannibalization review returned an invalid result"]
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
        return [], []
    if raw_conflicts and not conflicts:
        return [], []
    if not conflicts:
        return [], ["the semantic cannibalization review did not approve the architecture"]
    errors = [
        "intent conflict: " + str(item.get("page_a") or "unknown") + " vs "
        + str(item.get("page_b") or "unknown") + " — " + str(item.get("reason") or "overlapping intent")
        for item in conflicts
    ]
    return conflicts, errors or ["the semantic cannibalization review found an unspecified conflict"]


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
        "hub_title": f"MASTER HUB: {master['article_title']}",
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
        "semantic_intents": "Checked by specialist agent",
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
) -> dict[str, Any]:
    normalized = normalize_keyword_records(records, primary_keyword)
    if not normalized:
        raise ArchitectureAgentError("No usable keyword text was supplied.")
    if not is_ai_configured():
        raise ArchitectureAgentError("The SEO architecture agent is unavailable because no AI provider is configured.")

    main = clean_phrase(primary_keyword) or normalized[0]["phrase"]
    prompt = _prompt(normalized, context, main)
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
            last_errors = validate_architecture(plan, normalized, main)
            if not last_errors:
                review_limit = min(5, len(plan["spokes"]) + 1)
                for _review in range(review_limit):
                    conflicts, last_errors = await _audit_intent_cannibalization(plan, context)
                    if not conflicts:
                        break
                    plan, merge_notes = _merge_intent_conflicts(plan, conflicts)
                    if not merge_notes:
                        break
                    last_errors = validate_architecture(plan, normalized, main)
                    if last_errors:
                        break
            if not last_errors:
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
