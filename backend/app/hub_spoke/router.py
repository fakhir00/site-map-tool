import json
import uuid
from copy import deepcopy
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models import HubSpokeHistory, Keyword, KeywordUrl, Project, Url, User
from nlp.hub_spoke_agent import ArchitectureAgentError, build_site_architecture, normalize_keyword_records, usable_keywords
from nlp.keywords import clean_phrase, is_publishable_keyword, normalize_seed_keywords

router = APIRouter(prefix="/api/hub-spoke", tags=["hub-spoke-workspace"])


class KeywordMetricInput(BaseModel):
    phrase: str
    keyword_type: str = "long-tail"
    search_volume: int | None = None
    difficulty: float | None = None
    frequency: int = 1
    source_domains: list[str] = Field(default_factory=list)


class KeywordWorkspaceRequest(BaseModel):
    keywords: list[str] = Field(min_length=1, max_length=5000)
    keyword_data: list[KeywordMetricInput] = Field(default_factory=list, max_length=5000)
    context: str = Field(default="", max_length=12000)
    primary_keyword: str = Field(default="", max_length=300)
    existing_urls: list[HttpUrl] = Field(default_factory=list, max_length=100)
    project_id: uuid.UUID | None = None


class HubSpokeHistorySummary(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID | None
    title: str
    keyword_count: int
    created_at: datetime


def _history_payload(record: HubSpokeHistory) -> dict[str, Any]:
    return {
        "id": record.id, "project_id": record.project_id, "title": record.title,
        "context": _hub_spoke_context(record.context or ""), "keywords": record.keywords or [],
        "cleaned_keywords": record.cleaned_keywords or [], "clusters": record.mapping_data,
        "created_at": record.created_at,
    }


def _basic_clean(values: list[str]) -> list[str]:
    """Parse and normalize uploaded text without making SEO relevance decisions."""
    result: list[str] = []
    for value in values:
        for raw in str(value).replace("\r", "\n").split("\n"):
            phrase = clean_phrase(raw.split(",", 1)[0].strip().strip('"'))
            if is_publishable_keyword(phrase, min_words=1) and phrase not in result:
                result.append(phrase)
    return result


def _primary_keyword_from_context(context: str) -> str:
    try:
        payload = json.loads(context) if context.strip() else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return ""
    return clean_phrase(str(payload.get("primary_keyword") or "")) if isinstance(payload, dict) else ""


def _context_with_seed_keywords(
    context: str, seed_keywords: list[str], site_domain: str = "",
) -> str:
    seeds = normalize_seed_keywords(seed_keywords)
    try:
        parsed = json.loads(context) if context.strip() else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        parsed = {"audit_summary": context.strip()} if context.strip() else {}
    if not isinstance(parsed, dict):
        parsed = {"audit_summary": context.strip()}
    competitor_profile = parsed.pop("competitor_profile", None)
    if competitor_profile:
        parsed["competitor_exclusions"] = competitor_profile
    parsed["seed_keywords"] = seeds
    if seeds and not parsed.get("primary_keyword"):
        parsed["primary_keyword"] = seeds[0]
    if site_domain:
        parsed["domain"] = site_domain
    return json.dumps(parsed, indent=2)


def _hub_spoke_context(context: str) -> str:
    try:
        parsed = json.loads(context) if context.strip() else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return context
    if not isinstance(parsed, dict):
        return context
    competitor_profile = parsed.pop("competitor_profile", None)
    if competitor_profile:
        parsed["competitor_exclusions"] = competitor_profile
    audit = parsed.get("audit_summary")
    if isinstance(audit, dict):
        nested_competitors = audit.pop("competitor_profile", None)
        if nested_competitors:
            parsed["competitor_exclusions"] = nested_competitors
    return json.dumps(parsed, indent=2)


def _keyword_records(body: KeywordWorkspaceRequest) -> list[dict[str, Any]]:
    metrics = {clean_phrase(item.phrase): item for item in body.keyword_data if clean_phrase(item.phrase)}
    records = [{
        "phrase": phrase,
        "type": metrics[phrase].keyword_type if phrase in metrics else "long-tail",
        "search_volume": metrics[phrase].search_volume if phrase in metrics else None,
        "difficulty": metrics[phrase].difficulty if phrase in metrics else None,
        "frequency": metrics[phrase].frequency if phrase in metrics else 1,
        "source_domains": metrics[phrase].source_domains if phrase in metrics else [],
    } for phrase in _basic_clean(body.keywords)]
    return normalize_keyword_records(records, body.primary_keyword or _primary_keyword_from_context(body.context))


@router.post("/build")
async def build_uploaded_hub_spoke(
    body: KeywordWorkspaceRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.project_id:
        owned = await db.execute(select(Project.id).where(Project.id == body.project_id, Project.user_id == current_user.id))
        if owned.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="Project not found")
    context = _hub_spoke_context(body.context)
    if body.primary_keyword.strip() or body.existing_urls:
        try:
            payload = json.loads(context) if context else {}
        except (ValueError, TypeError):
            payload = {"audit_summary": context}
        if not isinstance(payload, dict):
            payload = {"audit_summary": context}
        if body.primary_keyword.strip():
            payload["primary_keyword"] = clean_phrase(body.primary_keyword)
        if body.existing_urls:
            declared = [{"url": str(url), "evidence": "user_supplied_url"} for url in body.existing_urls]
            previous = payload.get("owned_pages")
            payload["owned_pages"] = (previous if isinstance(previous, list) else []) + declared
        context = json.dumps(payload)
    saved_context = context
    if body.project_id:
        from app.hub_spoke.context import context_with_owned_pages
        context = await context_with_owned_pages(db, body.project_id, context)
    records = _keyword_records(body)
    if not records:
        raise HTTPException(status_code=422, detail="Upload at least one readable keyword.")
    if len(records) > 300:
        raise HTTPException(status_code=422, detail="Use at most 300 distinct keywords per map, including the main topic. Narrow the list to one focused subject.")
    primary = _primary_keyword_from_context(context) or records[0]["phrase"]
    try:
        mapping = await build_site_architecture(records, context=context, primary_keyword=primary, discover_topics=True)
    except ArchitectureAgentError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    kept = usable_keywords(mapping)
    title = str(mapping["master_hub"].get("article_title") or primary.title())[:255]
    history = HubSpokeHistory(
        user_id=current_user.id, project_id=body.project_id, title=title, context=saved_context,
        keywords=[item["phrase"] for item in records], cleaned_keywords=kept, mapping_data=mapping,
    )
    db.add(history)
    await db.flush()
    await db.refresh(history)
    return {"keywords": kept, "keyword_data": mapping.get("_keyword_metrics", records), "count": len(kept), "clusters": mapping, "history_id": history.id}


@router.get("/project-import/{project_id}")
async def import_project_keywords(
    project_id: uuid.UUID,
    primary_keyword: str = "",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Project).where(Project.id == project_id, Project.user_id == current_user.id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    context = _context_with_seed_keywords(
        project.audit_summary or "", project.target_keywords or [], project.own_domain or project.domain,
    )
    canonical_primary = _primary_keyword_from_context(context)
    rows = await db.execute(
        select(Keyword.id, Keyword.phrase, Keyword.keyword_type, Keyword.search_volume, Keyword.difficulty, Keyword.frequency)
        .where(Keyword.project_id == project.id)
        .order_by(Keyword.frequency.desc(), Keyword.created_at.asc()).limit(5000)
    )
    keyword_rows = rows.all()
    source_domains: dict[uuid.UUID, set[str]] = {}
    if keyword_rows:
        sources = await db.execute(select(KeywordUrl.keyword_id, Url.url).join(Url, Url.id == KeywordUrl.url_id).where(
            KeywordUrl.keyword_id.in_([row[0] for row in keyword_rows]),
            Url.project_id == project.id, Url.source_type == "competitor",
        ))
        from urllib.parse import urlparse
        for keyword_id, url in sources.all():
            host = urlparse(url).hostname
            if host:
                source_domains.setdefault(keyword_id, set()).add(host)
    records = [{
        "phrase": phrase, "type": keyword_type, "search_volume": search_volume,
        "difficulty": difficulty, "frequency": frequency, "source_domains": sorted(source_domains.get(keyword_id, set())),
    } for keyword_id, phrase, keyword_type, search_volume, difficulty, frequency in keyword_rows]
    # Architecture needs the existing site as well as missing topics. Import
    # owned titles as planning inventory, never persist them as new keyword gaps.
    own_titles = await db.execute(select(Url.h1).where(
        Url.project_id == project.id, Url.source_type == "own", Url.status == "scraped",
        Url.h1.is_not(None),
    ).order_by(Url.url).limit(200))
    records.extend({"phrase": title, "type": "heading", "search_volume": None, "difficulty": None}
                   for title in own_titles.scalars().all() if is_publishable_keyword(title, min_words=2))
    keyword_data = normalize_keyword_records(records, canonical_primary)
    selected = clean_phrase(primary_keyword) or canonical_primary
    keyword_data.sort(key=lambda item: item["phrase"] != selected)
    if not keyword_data:
        raise HTTPException(status_code=404, detail="This Gap Hunter scan has no keywords to import yet.")
    return {
        "project_id": project.id, "project_name": project.name,
        "keywords": [item["phrase"] for item in keyword_data], "keyword_data": keyword_data,
        "context": context,
    }


@router.get("/history", response_model=list[HubSpokeHistorySummary])
async def list_hub_spoke_history(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(HubSpokeHistory.id, HubSpokeHistory.project_id, HubSpokeHistory.title,
               HubSpokeHistory.cleaned_keywords, HubSpokeHistory.created_at)
        .where(HubSpokeHistory.user_id == current_user.id)
        .order_by(desc(HubSpokeHistory.created_at)).limit(50)
    )
    return [{"id": history_id, "project_id": project_id, "title": title,
             "keyword_count": len(cleaned_keywords or []), "created_at": created_at}
            for history_id, project_id, title, cleaned_keywords, created_at in result.all()]


@router.get("/history/{history_id}")
async def get_hub_spoke_history(
    history_id: uuid.UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(HubSpokeHistory).where(
        HubSpokeHistory.id == history_id, HubSpokeHistory.user_id == current_user.id,
    ))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Hub Spoke history not found")
    # Recheck saved plans against the latest crawl so a newly discovered page
    # cannot remain a "create" recommendation in an older map.
    from app.hub_spoke.context import context_with_owned_pages
    from nlp.authority import reconcile_owned_pages
    payload = _history_payload(record)
    context = payload['context']
    if record.project_id:
        context = await context_with_owned_pages(db, record.project_id, context)
    payload['clusters'] = reconcile_owned_pages(deepcopy(payload['clusters'] or {}), context, strict=False)
    return payload


@router.delete("/history/{history_id}", status_code=204)
async def delete_hub_spoke_history(
    history_id: uuid.UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    result = await db.execute(delete(HubSpokeHistory).where(
        HubSpokeHistory.id == history_id, HubSpokeHistory.user_id == current_user.id,
    ))
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Hub Spoke history not found")
