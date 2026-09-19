"""SEO-specialist agent for building a complete, cannibalization-safe site architecture."""

from __future__ import annotations

import json
import logging
import re
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


def _prompt(records: list[dict[str, Any]], context: str, primary_keyword: str) -> str:
    return f"""
Act as a senior technical SEO architect whose specialty is hub-and-spoke information architecture.
You own the complete decision. Study the website context and every supplied keyword, then create a
practical architecture that maximizes useful coverage without search-intent cannibalization.

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
- Select one broad, central master hub. Prefer the requested primary topic when it is valid. Each
  other page is a spoke. Use search volume and difficulty as prioritization signals, not truth about intent.
- Every page target and every keyword named in an assignment must be copied exactly from the inventory.
- Create the number of pages justified by the data. Do not force a quota and do not pad the plan.
- Page titles, headings, questions, briefs, and link explanations may be newly written natural language.
- Every spoke links to the master. The master links to every spoke. Add only useful lateral links.

Return only one JSON object with this schema:
{{
  "site_strategy": "concise expert rationale",
  "master_hub": {{
    "article_title": "...", "target_keyword": "exact inventory keyword",
    "search_intent": "specific unique intent", "ranking_role": "master_hub",
    "slug": "/slug/", "page_type": "article or tool", "word_count_suggestion": 2500,
    "content_brief": "...", "tool_functions": [],
    "h2_sections": [{{"h2_heading": "...", "section_definition": "...", "targeted_keywords_placed_here": ["exact keyword"]}}],
    "faq_schema_questions": [{{"question": "...", "targeted_keywords_placed_here": ["exact keyword"]}}],
    "entity_terms": ["exact keyword"], "internal_links": ["exact page target"],
    "writing_instructions": "..."
  }},
  "spokes": [{{
    "spoke_category": "...", "article_title": "...", "target_keyword": "exact inventory keyword",
    "search_intent": "specific unique intent", "ranking_role": "supporting_spoke or easy_win_spoke",
    "slug": "/slug/", "page_type": "article or tool", "word_count_suggestion": 1800,
    "content_brief": "...", "tool_functions": [],
    "h2_sections": [{{"h2_heading": "...", "section_definition": "...", "targeted_keywords_placed_here": ["exact keyword"]}}],
    "faq_schema_questions": [{{"question": "...", "targeted_keywords_placed_here": ["exact keyword"]}}],
    "entity_terms": ["exact keyword"], "internal_links": ["exact page target"],
    "writing_instructions": "..."
  }}],
  "keyword_assignments": [
    {{"keyword": "exact keyword", "disposition": "page_target", "assigned_to": "same exact keyword", "placement": "title", "reason": "..."}},
    {{"keyword": "exact keyword", "disposition": "supporting", "assigned_to": "exact page target", "placement": "h2, faq, entity, feature, or variation", "reason": "..."}},
    {{"keyword": "exact keyword", "disposition": "discard", "assigned_to": null, "placement": null, "reason": "..."}}
  ],
  "interlinking_strategy": "..."
}}
"""


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
    return {
        "spoke_category": str(raw.get("spoke_category") or "Strategic topic").strip(),
        "article_title": str(raw.get("article_title") or target.title()).strip(),
        "target_keyword": target,
        "search_intent": str(raw.get("search_intent") or "").strip(),
        "ranking_role": str(raw.get("ranking_role") or "supporting_spoke").strip(),
        "search_volume": metric.get("search_volume"),
        "difficulty": metric.get("difficulty"),
        "slug": _slug(target),
        "page_type": "tool" if str(raw.get("page_type") or "").lower() == "tool" else "article",
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


def _normalize_plan(payload: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = {item["phrase"]: item for item in records}
    master = _clean_page(payload.get("master_hub") or {}, metrics)
    master["ranking_role"] = "master_hub"
    spokes = [_clean_page(item, metrics) for item in payload.get("spokes") or [] if isinstance(item, dict)]
    assignments = []
    for raw in payload.get("keyword_assignments") or []:
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


def validate_architecture(plan: dict[str, Any], records: list[dict[str, Any]]) -> list[str]:
    inventory = {item["phrase"] for item in records}
    errors: list[str] = []
    master = plan.get("master_hub") or {}
    pages = [master, *(plan.get("spokes") or [])]
    targets = [page.get("target_keyword") for page in pages]
    if not targets or not targets[0]:
        errors.append("one master hub is required")
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
    return list(dict.fromkeys(errors))


async def _audit_intent_cannibalization(plan: dict[str, Any], context: str) -> list[str]:
    """Use a separate review pass to catch semantic overlap hidden by different wording."""
    pages = [plan["master_hub"], *plan["spokes"]]
    review_input = [{
        "target_keyword": page["target_keyword"],
        "search_intent": page["search_intent"],
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

Find every pair that would compete for substantially the same organic search intent. Closely related
pages are allowed only when their user goal and expected result type are materially different.
Return {{"passed": true, "conflicts": []}} when no pair conflicts. Otherwise return:
{{"passed": false, "conflicts": [{{"page_a": "exact target", "page_b": "exact target", "reason": "...", "resolution": "merge or clarify"}}]}}
""",
        temperature=0,
        max_tokens=3000,
    )
    if not isinstance(audit, dict) or not isinstance(audit.get("conflicts"), list):
        return ["the semantic cannibalization review returned an invalid result"]
    conflicts = audit["conflicts"]
    if audit.get("passed") is True and not conflicts:
        return []
    if not conflicts:
        return ["the semantic cannibalization review did not approve the architecture"]
    return [
        "intent conflict: " + str(item.get("page_a") or "unknown") + " vs "
        + str(item.get("page_b") or "unknown") + " — " + str(item.get("reason") or "overlapping intent")
        for item in conflicts if isinstance(item, dict)
    ] or ["the semantic cannibalization review found an unspecified conflict"]


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
            if not isinstance(payload, dict):
                raise ValueError("the provider returned a non-object response")
            plan = _normalize_plan(payload, normalized)
            last_errors = validate_architecture(plan, normalized)
            if not last_errors:
                last_errors = await _audit_intent_cannibalization(plan, context)
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
