import json
import math
import re
import uuid
from collections import Counter
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models import HubSpokeHistory, Keyword, Project, User
from nlp.keywords import (
    BROAD_TOPIC_TERMS,
    STOPWORDS,
    clean_phrase,
    is_publishable_keyword,
    is_topic_relevant_keyword,
    keyword_terms,
    normalize_seed_keywords,
    seed_keyword_terms,
    site_scope_terms,
)
from nlp.openrouter import _achat_json, cluster_hub_and_spoke, is_ai_configured

router = APIRouter(prefix="/api/hub-spoke", tags=["hub-spoke-workspace"])


class KeywordMetricInput(BaseModel):
    phrase: str
    keyword_type: str = "long-tail"
    search_volume: int | None = None
    difficulty: float | None = None
    frequency: int = 1


class KeywordWorkspaceRequest(BaseModel):
    keywords: list[str] = Field(min_length=1, max_length=5000)
    keyword_data: list[KeywordMetricInput] = Field(default_factory=list, max_length=5000)
    context: str = Field(default="", max_length=12000)
    project_id: uuid.UUID | None = None


class HubSpokeHistorySummary(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID | None
    title: str
    keyword_count: int
    created_at: datetime


def _history_payload(record: HubSpokeHistory) -> dict[str, Any]:
    return {
        "id": record.id,
        "project_id": record.project_id,
        "title": record.title,
        "context": _hub_spoke_context(record.context or ""),
        "keywords": record.keywords or [],
        "cleaned_keywords": record.cleaned_keywords or [],
        "clusters": record.mapping_data,
        "created_at": record.created_at,
    }


def _basic_clean(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        for raw in str(value).replace("\r", "\n").split("\n"):
            # CSV rows commonly contain a keyword in the first column.
            phrase = clean_phrase(raw.split(",", 1)[0].strip().strip('"'))
            if not is_publishable_keyword(phrase, min_words=1) or phrase in result:
                continue
            result.append(phrase)
    return result


def _keyword_records(body: KeywordWorkspaceRequest, cleaned: list[str]) -> list[dict[str, Any]]:
    """Keep SEO metrics attached to their phrase through cleaning and planning."""
    metrics = {
        clean_phrase(item.phrase): item
        for item in body.keyword_data
        if clean_phrase(item.phrase)
    }
    return [{
        "phrase": phrase,
        "type": metrics[phrase].keyword_type if phrase in metrics else "long-tail",
        "search_volume": metrics[phrase].search_volume if phrase in metrics else None,
        "difficulty": metrics[phrase].difficulty if phrase in metrics else None,
        "frequency": metrics[phrase].frequency if phrase in metrics else 1,
    } for phrase in cleaned]


def _context_anchor_terms(context: str) -> set[str]:
    """Extract concrete topic signals for the no-AI cleaning fallback."""
    from nlp.keywords import STOPWORDS

    generic = {
        "website", "product", "service", "audience", "customer", "customers",
        "content", "company", "business", "online", "platform", "people",
        "provide", "provides", "target", "topic", "topics", "user", "users",
    }
    return {
        token[:-1] if token.endswith("s") and len(token) > 4 else token
        for token in re.findall(r"[a-z0-9]+", context.lower())
        if len(token) >= 4 and token not in STOPWORDS and token not in generic
    }


def _fallback_context_filter(keywords: list[str], context: str) -> list[str]:
    anchors = _context_anchor_terms(context)
    if not anchors:
        return keywords
    result: list[str] = []
    for phrase in keywords:
        terms = {
            token[:-1] if token.endswith("s") and len(token) > 4 else token
            for token in re.findall(r"[a-z0-9]+", phrase.lower())
        }
        if terms & anchors:
            result.append(phrase)
    return result


def _primary_keyword_from_context(context: str) -> str:
    """Read the explicit seed from JSON or JSON-like audit context."""
    if not context.strip():
        return ""
    try:
        payload = json.loads(context)
        if isinstance(payload, dict):
            value = payload.get("primary_keyword")
            if value:
                return clean_phrase(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    match = re.search(r'["\']?primary[_\s-]*keyword["\']?\s*:\s*["\']([^"\'\n,}]+)', context, re.IGNORECASE)
    return clean_phrase(match.group(1)) if match else ""


def _seed_keywords_from_context(context: str) -> list[str]:
    """Return every authoritative seed embedded in Hub Spoke context."""
    values: list[str] = []
    try:
        payload = json.loads(context)
    except (TypeError, ValueError, json.JSONDecodeError):
        payload = None
    if isinstance(payload, dict):
        values.append(str(payload.get("primary_keyword") or ""))
        for item in payload.get("seed_keywords", []) or []:
            values.append(str(item.get("keyword") if isinstance(item, dict) else item))
        for item in payload.get("seeds", []) or []:
            values.append(str(item.get("keyword") if isinstance(item, dict) else item))
    else:
        values.append(_primary_keyword_from_context(context))
    return normalize_seed_keywords(values)


def _context_with_seed_keywords(context: str, seed_keywords: list[str]) -> str:
    """Expose project seeds in the editable context sent to Hub Spoke."""
    seeds = normalize_seed_keywords(seed_keywords)
    try:
        parsed = json.loads(context) if context.strip() else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        parsed = {"audit_summary": context.strip()} if context.strip() else {}
    if not isinstance(parsed, dict):
        parsed = {"audit_summary": context.strip()}
    parsed.pop("competitor_profile", None)
    parsed["seed_keywords"] = seeds
    if seeds and not parsed.get("primary_keyword"):
        parsed["primary_keyword"] = seeds[0]
    return json.dumps(parsed, indent=2)


def _hub_spoke_context(context: str) -> str:
    """Remove competitor framing so the site's own EMD and seeds define scope."""
    try:
        parsed = json.loads(context) if context.strip() else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return context
    if not isinstance(parsed, dict):
        return context
    parsed.pop("competitor_profile", None)
    audit = parsed.get("audit_summary")
    if isinstance(audit, dict):
        audit.pop("competitor_profile", None)
    return json.dumps(parsed, indent=2)


def _structured_context(context: str) -> dict[str, Any]:
    try:
        value = json.loads(context) if context.strip() else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _term_family(term: str) -> str:
    """Small deterministic stemmer used only for scope and boundary checks."""
    aliases = {
        "electrical": "electric", "electronic": "electric", "electronics": "electric",
        "diagrams": "diagram", "drawings": "drawing", "symbols": "symbol",
        "wiring": "wire",
    }
    value = aliases.get(term, term)
    for suffix in ("ations", "ation", "ators", "ator", "ments", "ment", "ing", "ers", "er", "ed"):
        if value.endswith(suffix) and len(value) - len(suffix) >= 4:
            value = value[:-len(suffix)]
            if len(value) > 3 and value[-1:] == value[-2:-1]:
                value = value[:-1]
            break
    return value


def _hard_boundary_families(context_data: dict[str, Any], protected_terms: set[str]) -> set[str]:
    boilerplate = {
        "does", "provide", "provides", "serve", "serves", "offer", "offers",
        "other", "purpose", "purposes", "general", "personalized",
    }
    families: set[str] = set()
    for boundary in context_data.get("hard_boundaries", []) or []:
        for token in clean_phrase(str(boundary)).split():
            if token in STOPWORDS or token in boilerplate or len(token) < 2:
                continue
            families.add(_term_family(token))
    return families - {_term_family(term) for term in protected_terms}


def _violates_hard_boundary(phrase: str, boundary_families: set[str]) -> bool:
    phrase_families = {_term_family(token) for token in clean_phrase(phrase).split()}
    return bool(phrase_families & boundary_families)


def _mechanical_relevance_filter(keywords: list[str], context: str) -> list[str]:
    """Reject isolated off-topic phrases without relying on the AI provider."""
    if not keywords:
        return []
    term_sets = {phrase: keyword_terms(phrase, min_len=2) for phrase in keywords}
    document_frequency = Counter(term for terms in term_sets.values() for term in terms)
    threshold = max(2, math.ceil(len(keywords) * 0.08))
    dominant_terms = {term for term, count in document_frequency.items() if count >= threshold}
    context_terms = keyword_terms(context, min_len=2) if context.strip() else set()
    positions = {phrase: index for index, phrase in enumerate(keywords)}
    seed_keywords = _seed_keywords_from_context(context)
    context_data = _structured_context(context)
    primary_keyword = _primary_keyword_from_context(context) or (seed_keywords[0] if seed_keywords else "")
    scope_terms = site_scope_terms(primary_keyword, context_data)
    topic_profile = context_terms | {f"__scope__{term}" for term in scope_terms}
    protected_terms = set(clean_phrase(primary_keyword).split()) | scope_terms
    boundary_families = _hard_boundary_families(context_data, protected_terms)
    content_intent_terms = {
        "comparison", "definition", "example", "examples", "guide", "meaning",
        "reference", "review", "symbol", "symbols", "tutorial", "types",
    }

    def inside_context(phrase: str) -> bool:
        if _violates_hard_boundary(phrase, boundary_families):
            return False
        if not primary_keyword:
            return True
        if is_topic_relevant_keyword(phrase, seed_keywords or [primary_keyword], topic_profile):
            return True
        phrase_terms = keyword_terms(phrase, min_len=2)
        for seed in seed_keywords[1:]:
            seed_terms = keyword_terms(seed, min_len=2) - BROAD_TOPIC_TERMS
            if seed_terms and phrase_terms & seed_terms:
                return True
        raw = set(clean_phrase(phrase).split())
        primary_anchors = seed_keyword_terms([primary_keyword]) - BROAD_TOPIC_TERMS
        if raw & primary_anchors and raw & content_intent_terms:
            return True
        raw_families = {_term_family(term) for term in raw}
        scope_families = {_term_family(term) for term in scope_terms}
        # Two audited scope signals form the permitted two-hop route for close
        # terms that do not repeat the EMD wording.
        return len(raw_families & scope_families) >= 2

    if primary_keyword:
        return [phrase for phrase in keywords if inside_context(phrase)]

    seed_rules: list[tuple[set[str], int]] = []
    for seed in seed_keywords:
        seed_terms = keyword_terms(seed, min_len=2)
        distinctive_terms = seed_terms - BROAD_TOPIC_TERMS
        required_terms = distinctive_terms or seed_terms
        if required_terms:
            required_overlap = 1 if distinctive_terms or len(required_terms) == 1 else 2
            seed_rules.append((required_terms, required_overlap))

    if seed_rules:
        # Never allow a candidate list to redefine an explicit site topic. If
        # no candidate contains any seed's defining term, the correct result is an
        # empty list and a clear 422 response rather than an off-topic plan.
        def matches_seed(terms: set[str]) -> bool:
            return any(len(terms & required) >= overlap for required, overlap in seed_rules)

        if not any(matches_seed(terms) for terms in term_sets.values()):
            return []
        return [
            phrase for phrase in keywords
            if matches_seed(term_sets[phrase])
        ]

    def anchor_score(phrase: str) -> tuple[int, int]:
        terms = term_sets[phrase]
        return (
            len(terms & context_terms),
            sum(document_frequency[term] for term in terms) * len(keywords) - positions[phrase],
        )

    anchor = max(keywords, key=anchor_score)
    anchor_terms = term_sets[anchor]
    if not anchor_terms and not context_terms and not dominant_terms:
        return keywords

    relevant: list[str] = []
    for phrase in keywords:
        terms = term_sets[phrase]
        anchor_overlap = terms & anchor_terms
        context_overlap = terms & context_terms
        dominant_overlap = terms & dominant_terms
        if (
            phrase == anchor
            or anchor_overlap
            or len(context_overlap) >= 2
            or (context_overlap and dominant_overlap)
            or (not context_terms and dominant_overlap)
        ):
            relevant.append(phrase)
    return relevant


async def _clean_with_context(keywords: list[str], context: str) -> list[str]:
    cleaned = _basic_clean(keywords)
    if not cleaned:
        return cleaned
    if not is_ai_configured():
        return _mechanical_relevance_filter(cleaned, context)

    accepted: list[str] = []
    for start in range(0, len(cleaned), 100):
        chunk = cleaned[start:start + 100]
        prompt = f"""
You are a strict SEO keyword-list cleaner.

Website/product context:
{context or "No extra context. Infer the dominant topic shared by the keyword list."}

Candidate keywords:
{json.dumps(chunk)}

Treat the primary keyword/EMD as the central entity and allow at most two semantic hops from it.
Keep a candidate only when the site context gives a concrete reason to satisfy that exact search
intent. Enforce every hard boundary literally. Reject adjacent industries, unsupported product
functions, courseware/file-download queries, answer keys, manuals, brand drift, navigation text,
broken phrases, and extraction junk. Shared generic words such as circuit, age, system, maker,
calculator, software, or diagram are never sufficient evidence by themselves. When uncertain,
reject the candidate. Precision is more important than list size.
You may only return exact strings from Candidate keywords. Order the strongest primary topic first.
Return JSON: {{"keywords": ["exact candidate", "exact candidate"]}}
"""
        try:
            payload = await _achat_json(
                system_prompt="Return only valid JSON and never invent a keyword.",
                user_prompt=prompt,
                temperature=0.1,
                max_tokens=3500,
            )
        except Exception:
            payload = None
        selected = payload.get("keywords") if isinstance(payload, dict) else None
        if not isinstance(selected, list):
            accepted.extend(_fallback_context_filter(chunk, context) if context.strip() else chunk)
            continue
        allowed = set(chunk)
        for item in selected:
            phrase = clean_phrase(str(item))
            if phrase in allowed:
                accepted.append(phrase)
    return _mechanical_relevance_filter(list(dict.fromkeys(accepted)), context)


@router.post("/clean")
async def clean_uploaded_keywords(
    body: KeywordWorkspaceRequest,
    _current_user: User = Depends(get_current_user),
):
    context = _hub_spoke_context(body.context)
    keywords = await _clean_with_context(body.keywords, context)

    if keywords:
        from nlp.openrouter import _hub_same_page_intent
        vol_lookup = {item.phrase: (item.search_volume or 0) for item in body.keyword_data}
        deduped = []
        for kw in keywords:
            vol = vol_lookup.get(kw, 0)
            existing_idx = None
            for i, existing_kw in enumerate(deduped):
                if _hub_same_page_intent(kw, existing_kw):
                    existing_idx = i
                    break
            if existing_idx is not None:
                existing_kw = deduped[existing_idx]
                existing_vol = vol_lookup.get(existing_kw, 0)
                if vol > existing_vol:
                    deduped[existing_idx] = kw
            else:
                deduped.append(kw)
        keywords = deduped

    if not keywords:
        primary_keyword = _primary_keyword_from_context(context)
        detail = (
            f"No keywords matching the primary topic '{primary_keyword}' remained after cleaning. "
            "The source list must contain that topic or a verified semantic equivalent."
            if primary_keyword else "No relevant keywords remained after cleaning."
        )
        raise HTTPException(status_code=422, detail=detail)
    return {"keywords": keywords, "keyword_data": _keyword_records(body, keywords), "count": len(keywords)}


@router.post("/build")
async def build_uploaded_hub_spoke(
    body: KeywordWorkspaceRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project_id = body.project_id
    if project_id:
        project_result = await db.execute(select(Project.id).where(
            Project.id == project_id,
            Project.user_id == current_user.id,
        ))
        if project_result.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="Project not found")
    context = _hub_spoke_context(body.context)
    keywords = await _clean_with_context(body.keywords, context)
    if not keywords:
        primary_keyword = _primary_keyword_from_context(context)
        detail = (
            f"The keyword list does not contain usable keywords for the primary topic '{primary_keyword}'."
            if primary_keyword else "Upload a keyword list with at least one usable keyword."
        )
        raise HTTPException(status_code=422, detail=detail)
    rejected_keywords = [phrase for phrase in _basic_clean(body.keywords) if phrase not in set(keywords)]
    typed = _keyword_records(body, keywords)
    main_keyword = _primary_keyword_from_context(context)
    if not main_keyword:
        context_seeds = _seed_keywords_from_context(context)
        main_keyword = context_seeds[0] if context_seeds else keywords[0]
    mapping = await cluster_hub_and_spoke(
        typed,
        main_keyword=main_keyword,
        audit_summary=context or "Uploaded keyword research list",
    )
    if not mapping:
        raise HTTPException(status_code=502, detail="Could not build a constraint-safe hub-spoke map from this list.")
    if isinstance(mapping, dict) and rejected_keywords:
        mapping["filtered_irrelevant_keywords"] = list(dict.fromkeys([
            *(mapping.get("filtered_irrelevant_keywords") or []),
            *rejected_keywords,
        ]))
    if isinstance(mapping, dict):
        mapping["_keyword_metrics"] = typed
    master = mapping.get("master_hub") if isinstance(mapping, dict) else None
    title = str((master or {}).get("article_title") or keywords[0].title())[:255]
    history = HubSpokeHistory(
        user_id=current_user.id,
        project_id=project_id,
        title=title,
        context=context,
        keywords=body.keywords,
        cleaned_keywords=keywords,
        mapping_data=mapping,
    )
    db.add(history)
    await db.flush()
    await db.refresh(history)
    return {
        "keywords": keywords,
        "keyword_data": typed,
        "count": len(keywords),
        "clusters": mapping,
        "history_id": history.id,
    }


@router.get("/project-import/{project_id}")
async def import_project_keywords(
    project_id: uuid.UUID,
    primary_keyword: str = "",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project_result = await db.execute(select(Project).where(
        Project.id == project_id,
        Project.user_id == current_user.id,
    ))
    project = project_result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    result = await db.execute(
        select(
            Keyword.phrase,
            Keyword.keyword_type,
            Keyword.search_volume,
            Keyword.difficulty,
            Keyword.frequency,
        )
        .where(Keyword.project_id == project.id)
        .order_by(Keyword.frequency.desc(), Keyword.created_at.asc())
        .limit(5000)
    )
    keyword_data: list[dict[str, Any]] = []
    seen: set[str] = set()
    for phrase, keyword_type, search_volume, difficulty, frequency in result.all():
        normalized = clean_phrase(str(phrase or ""))
        if (
            not normalized
            or normalized in seen
            or not is_publishable_keyword(normalized, min_words=2)
        ):
            continue
        seen.add(normalized)
        keyword_data.append({
            "phrase": normalized,
            "keyword_type": keyword_type or "long-tail",
            "search_volume": search_volume,
            "difficulty": difficulty,
            "frequency": frequency or 1,
        })
    keywords = [item["phrase"] for item in keyword_data]
    selected = clean_phrase(primary_keyword)
    selected_keyword = next((keyword for keyword in keywords if clean_phrase(keyword) == selected), None)
    if selected_keyword:
        keywords = [selected_keyword, *(keyword for keyword in keywords if keyword != selected_keyword)]
        keyword_data.sort(key=lambda item: item["phrase"] != selected_keyword)
    if not keywords:
        raise HTTPException(status_code=404, detail="This Gap Hunter scan has no keywords to import yet.")
    return {
        "project_id": project.id,
        "project_name": project.name,
        "keywords": keywords,
        "keyword_data": keyword_data,
        "context": _context_with_seed_keywords(project.audit_summary or "", project.target_keywords or []),
    }


@router.get("/history", response_model=list[HubSpokeHistorySummary])
async def list_hub_spoke_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(
            HubSpokeHistory.id,
            HubSpokeHistory.project_id,
            HubSpokeHistory.title,
            HubSpokeHistory.cleaned_keywords,
            HubSpokeHistory.created_at,
        )
        .where(HubSpokeHistory.user_id == current_user.id)
        .order_by(desc(HubSpokeHistory.created_at))
        .limit(50)
    )
    return [{
        "id": history_id,
        "project_id": project_id,
        "title": title,
        "keyword_count": len(cleaned_keywords or []),
        "created_at": created_at,
    } for history_id, project_id, title, cleaned_keywords, created_at in result.all()]


@router.get("/history/{history_id}")
async def get_hub_spoke_history(
    history_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(HubSpokeHistory).where(
        HubSpokeHistory.id == history_id,
        HubSpokeHistory.user_id == current_user.id,
    ))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Hub Spoke history not found")
    return _history_payload(record)


@router.delete("/history/{history_id}", status_code=204)
async def delete_hub_spoke_history(
    history_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(delete(HubSpokeHistory).where(
        HubSpokeHistory.id == history_id,
        HubSpokeHistory.user_id == current_user.id,
    ))
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Hub Spoke history not found")
