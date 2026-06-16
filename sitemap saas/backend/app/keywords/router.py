import uuid
import io
from typing import Optional
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import csv
from app.database import get_db
from app.models import User, Project, Keyword, KeywordUrl, Url, KeywordBank
from app.schemas import KeywordOut, KeywordListResponse, KeywordSourceOut, SaveKeywordRequest
from app.auth.jwt import get_current_user
from nlp.keywords import is_publishable_keyword, seed_keyword_terms
from nlp.openrouter import generate_ai_keywords

router = APIRouter(prefix="/api/projects", tags=["keywords"])
bank_router = APIRouter(prefix="/api/keyword-bank", tags=["keywords"])


@router.get("/{project_id}/keywords", response_model=KeywordListResponse)
async def list_keywords(
    project_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, le=200),
    sort_by: str = Query("frequency", enum=["frequency", "phrase", "created_at"]),
    keyword_type: Optional[str] = None,
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _assert_owns_project(project_id, current_user.id, db)
    topic_terms = seed_keyword_terms(project.target_keywords)

    q = select(Keyword).where(Keyword.project_id == project_id)
    if keyword_type:
        q = q.where(Keyword.keyword_type == keyword_type)
    if search:
        q = q.where(Keyword.phrase.ilike(f"%{search}%"))

    result = await db.execute(q)
    filtered_keywords = [
        keyword for keyword in result.scalars().all()
        if _is_displayable_keyword(keyword, topic_terms)
    ]

    if sort_by == "frequency":
        filtered_keywords.sort(key=lambda keyword: keyword.frequency, reverse=True)
    elif sort_by == "phrase":
        filtered_keywords.sort(key=lambda keyword: keyword.phrase)
    else:
        filtered_keywords.sort(key=lambda keyword: keyword.created_at, reverse=True)

    total = len(filtered_keywords)
    start = (page - 1) * page_size
    keywords = filtered_keywords[start:start + page_size]

    items = []
    for kw in keywords:
        sources = await _keyword_sources(db, kw.id, limit=10)
        kw_out = KeywordOut.model_validate(kw)
        kw_out.source_urls = [source.url for source in sources]
        kw_out.sources = sources
        items.append(kw_out)

    return KeywordListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=max(1, -(-total // page_size)),
    )


@router.post("/{project_id}/keywords/generate")
async def generate_keywords(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _assert_owns_project(project_id, current_user.id, db)
    if not project.target_keywords:
        raise HTTPException(status_code=400, detail="Project has no target keywords to generate from")
        
    ai_keywords = await generate_ai_keywords(project.target_keywords)
    if not ai_keywords:
        raise HTTPException(status_code=500, detail="Failed to generate AI keywords")
        
    # Get or create an AI source URL
    ai_url_str = "https://openrouter.ai/generated"
    q_url = select(Url).where(Url.project_id == project.id, Url.url == ai_url_str)
    result = await db.execute(q_url)
    ai_url = result.scalar_one_or_none()
    
    if not ai_url:
        ai_url = Url(
            project_id=project.id,
            url=ai_url_str,
            source_type="ai",
            source_domain="OpenRouter AI",
            status="scraped",
        )
        db.add(ai_url)
        await db.flush()
        
    added_count = 0
    for kw_data in ai_keywords:
        phrase = kw_data["phrase"]
        kw_type = kw_data["type"]
        
        q_kw = select(Keyword).where(Keyword.project_id == project.id, Keyword.phrase == phrase)
        result = await db.execute(q_kw)
        keyword = result.scalar_one_or_none()
        
        if not keyword:
            keyword = Keyword(
                project_id=project.id,
                phrase=phrase,
                keyword_type=kw_type,
                frequency=1,
            )
            db.add(keyword)
            await db.flush()
            added_count += 1
            
        # Link keyword to AI URL
        q_link = select(KeywordUrl).where(KeywordUrl.keyword_id == keyword.id, KeywordUrl.url_id == ai_url.id)
        result = await db.execute(q_link)
        link = result.scalar_one_or_none()
        if not link:
            db.add(KeywordUrl(keyword_id=keyword.id, url_id=ai_url.id))
            
    await db.commit()
    return {"message": f"Generated {added_count} new keywords", "generated": len(ai_keywords)}


@router.get("/{project_id}/keywords/export")
async def export_keywords(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _assert_owns_project(project_id, current_user.id, db)
    topic_terms = seed_keyword_terms(project.target_keywords)

    result = await db.execute(
        select(Keyword)
        .where(Keyword.project_id == project_id)
        .order_by(Keyword.frequency.desc())
    )
    keywords = [
        keyword for keyword in result.scalars().all()
        if _is_displayable_keyword(keyword, topic_terms)
    ]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Keyword Gap",
        "Type",
        "Competitor Pages",
        "Source Domains",
        "Source URLs",
        "Search Volume",
        "Difficulty",
    ])
    for kw in keywords:
        sources = await _keyword_sources(db, kw.id)
        source_domains = sorted(dict.fromkeys(_source_label(source) for source in sources))
        writer.writerow([
            kw.phrase,
            kw.keyword_type,
            kw.frequency,
            "; ".join(source_domains),
            "; ".join(source.url for source in sources),
            kw.search_volume or "",
            kw.difficulty or "",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=keywords-{project_id}.csv"},
    )


@router.post("/{project_id}/keywords/{keyword_id}/save", status_code=201)
async def save_keyword(
    project_id: uuid.UUID,
    keyword_id: uuid.UUID,
    body: SaveKeywordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _assert_owns_project(project_id, current_user.id, db)

    kw_result = await db.execute(
        select(Keyword).where(Keyword.id == keyword_id, Keyword.project_id == project_id)
    )
    if not kw_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Keyword not found")

    existing = await db.execute(
        select(KeywordBank).where(
            KeywordBank.user_id == current_user.id,
            KeywordBank.keyword_id == keyword_id,
        )
    )
    if existing.scalar_one_or_none():
        return {"message": "Already saved"}

    entry = KeywordBank(user_id=current_user.id, keyword_id=keyword_id, notes=body.notes)
    db.add(entry)
    return {"message": "Keyword saved to bank"}


@bank_router.get("")
async def get_keyword_bank(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(KeywordBank, Keyword)
        .join(Keyword, Keyword.id == KeywordBank.keyword_id)
        .where(KeywordBank.user_id == current_user.id)
        .order_by(KeywordBank.saved_at.desc())
    )
    rows = result.all()
    return [
        {
            "id": str(bank.id),
            "phrase": kw.phrase,
            "keyword_type": kw.keyword_type,
            "frequency": kw.frequency,
            "notes": bank.notes,
            "saved_at": bank.saved_at.isoformat(),
        }
        for bank, kw in rows
    ]


def _is_displayable_keyword(keyword: Keyword, topic_terms: set[str]) -> bool:
    return is_publishable_keyword(keyword.phrase, min_words=2, topic_terms=topic_terms)


async def _keyword_sources(
    db: AsyncSession,
    keyword_id: uuid.UUID,
    limit: int | None = None,
) -> list[KeywordSourceOut]:
    q = (
        select(Url.url, Url.source_type, Url.source_domain)
        .join(KeywordUrl, KeywordUrl.url_id == Url.id)
        .where(KeywordUrl.keyword_id == keyword_id)
        .order_by(Url.source_domain.asc().nullslast(), Url.url.asc())
    )
    if limit:
        q = q.limit(limit)
    result = await db.execute(q)
    return [
        KeywordSourceOut(
            url=url,
            source_type=source_type,
            source_domain=source_domain or _source_origin(url),
        )
        for url, source_type, source_domain in result.all()
    ]


def _source_label(source: KeywordSourceOut) -> str:
    return source.source_domain or _source_origin(source.url) or source.url


def _source_origin(url: str | None) -> str | None:
    if not url:
        return None
    value = url.strip()
    if not value:
        return None
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    parsed = urlparse(value)
    if not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


async def _assert_owns_project(project_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession) -> Project:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project
