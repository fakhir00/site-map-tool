import json
import re
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models import HubSpokeHistory, Keyword, Project, User
from nlp.keywords import clean_phrase, is_valid_keyword
from nlp.openrouter import _achat_json, cluster_hub_and_spoke, is_ai_configured

router = APIRouter(prefix="/api/hub-spoke", tags=["hub-spoke-workspace"])


class KeywordWorkspaceRequest(BaseModel):
    keywords: list[str] = Field(min_length=1, max_length=5000)
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
        "context": record.context or "",
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
            if not is_valid_keyword(phrase, min_words=1) or phrase in result:
                continue
            result.append(phrase)
    return result


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


async def _clean_with_context(keywords: list[str], context: str) -> list[str]:
    cleaned = _basic_clean(keywords)
    if not cleaned:
        return cleaned
    if not is_ai_configured():
        return _fallback_context_filter(cleaned, context) if context.strip() else cleaned

    accepted: list[str] = []
    for start in range(0, len(cleaned), 100):
        chunk = cleaned[start:start + 100]
        prompt = f"""
You are a strict SEO keyword-list cleaner.

Website/product context:
{context or "No extra context. Infer the dominant topic shared by the keyword list."}

Candidate keywords:
{json.dumps(chunk)}

Use a firm but balanced relevance threshold. Keep keywords that directly match the website and
also strongly related educational, comparison, feature, entity, audience, and use-case terms that
could support its topical authority. Reject clearly unrelated industries, impossible product
claims, brand drift, navigation text, broken phrases, and extraction junk. Do not reject a useful
keyword merely because it is adjacent to the core commercial phrase; keep it when the context
gives the site a credible reason to answer that search intent.
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
    return list(dict.fromkeys(accepted))


@router.post("/clean")
async def clean_uploaded_keywords(
    body: KeywordWorkspaceRequest,
    _current_user: User = Depends(get_current_user),
):
    keywords = await _clean_with_context(body.keywords, body.context)
    if not keywords:
        raise HTTPException(status_code=422, detail="No relevant keywords remained after cleaning.")
    return {"keywords": keywords, "count": len(keywords)}


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
    keywords = await _clean_with_context(body.keywords, body.context)
    if not keywords:
        raise HTTPException(status_code=422, detail="Upload a keyword list with at least one usable keyword.")
    typed = [{"phrase": phrase, "type": "long-tail"} for phrase in keywords]
    mapping = await cluster_hub_and_spoke(
        typed,
        main_keyword=keywords[0],
        audit_summary=body.context or "Uploaded keyword research list",
    )
    if not mapping:
        raise HTTPException(status_code=502, detail="Could not build a constraint-safe hub-spoke map from this list.")
    master = mapping.get("master_hub") if isinstance(mapping, dict) else None
    title = str((master or {}).get("article_title") or keywords[0].title())[:255]
    history = HubSpokeHistory(
        user_id=current_user.id,
        project_id=project_id,
        title=title,
        context=body.context,
        keywords=body.keywords,
        cleaned_keywords=keywords,
        mapping_data=mapping,
    )
    db.add(history)
    await db.flush()
    await db.refresh(history)
    return {
        "keywords": keywords,
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
        select(Keyword.phrase)
        .where(Keyword.project_id == project.id)
        .order_by(Keyword.frequency.desc(), Keyword.created_at.asc())
        .limit(5000)
    )
    keywords = list(dict.fromkeys(str(value).strip() for value in result.scalars().all() if str(value).strip()))
    selected = clean_phrase(primary_keyword)
    selected_keyword = next((keyword for keyword in keywords if clean_phrase(keyword) == selected), None)
    if selected_keyword:
        keywords = [selected_keyword, *(keyword for keyword in keywords if keyword != selected_keyword)]
    if not keywords:
        raise HTTPException(status_code=404, detail="This Gap Hunter scan has no keywords to import yet.")
    return {
        "project_id": project.id,
        "project_name": project.name,
        "keywords": keywords,
        "context": project.audit_summary or "",
    }


@router.get("/history", response_model=list[HubSpokeHistorySummary])
async def list_hub_spoke_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(HubSpokeHistory)
        .where(HubSpokeHistory.user_id == current_user.id)
        .order_by(desc(HubSpokeHistory.created_at))
        .limit(50)
    )
    return [{
        "id": record.id,
        "project_id": record.project_id,
        "title": record.title,
        "keyword_count": len(record.cleaned_keywords or []),
        "created_at": record.created_at,
    } for record in result.scalars().all()]


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
