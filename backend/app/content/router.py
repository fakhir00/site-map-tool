import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.auth.jwt import get_current_user
from app.content.service import generate_article_package, generate_final_article_package
from app.database import get_db
from app.models import ArticleDraft, Keyword, KeywordUrl, Project, Url, User
from app.schemas import ArticleDraftOut, ArticleListResponse

router = APIRouter(prefix="/api/projects", tags=["content"])


@router.post("/{project_id}/keywords/{keyword_id}/article/generate", response_model=ArticleDraftOut)
async def generate_article(
    project_id: uuid.UUID,
    keyword_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_user_project(project_id, current_user.id, db)
    keyword = await _get_project_keyword(project_id, keyword_id, db)

    competitor_urls = await _keyword_source_urls(
        db,
        project_id=project_id,
        keyword_id=keyword_id,
        source_type="competitor",
        limit=6,
    )
    own_urls = await _keyword_source_urls(
        db,
        project_id=project_id,
        keyword_id=keyword_id,
        source_type="own",
        limit=2,
    )
    if not competitor_urls:
        competitor_urls = await _fallback_project_urls(db, project_id, source_type="competitor", limit=6)
    if not own_urls:
        own_urls = await _fallback_project_urls(db, project_id, source_type="own", limit=2)

    try:
        package = await run_in_threadpool(
            generate_article_package,
            project_name=project.name,
            project_domain=project.domain,
            primary_keyword=keyword.phrase,
            seed_keywords=project.target_keywords or [keyword.phrase],
            competitor_urls=competitor_urls,
            own_urls=own_urls,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    draft = ArticleDraft(
        project_id=project.id,
        keyword_id=keyword.id,
        status=package["status"],
        title=package["title"],
        content_markdown=package["content_markdown"],
        audit_score=package["audit"].get("score") if package.get("audit") else None,
        generation_attempts=package["attempts"],
        research_summary={
            "brief": package["brief"],
            "competitor_pages": package["competitor_pages"],
            "own_pages": package["own_pages"],
        },
        audit_feedback=package.get("audit"),
    )
    db.add(draft)
    await db.flush()
    await db.refresh(draft)
    return _article_out(draft, keyword.phrase)


from pydantic import BaseModel, Field, field_validator
class ManualGenerateRequest(BaseModel):
    main_keyword: str = Field(min_length=1)
    keyword_cluster: str = ""
    architecture_brief: str = Field(default="", max_length=12000)
    project_id: uuid.UUID | None = None

    @field_validator("main_keyword", mode="before")
    @classmethod
    def strip_keyword(cls, value):
        return value.strip() if isinstance(value, str) else value

@router.post("/manual-generate", response_model=ArticleDraftOut)
async def manual_generate_article(
    req: ManualGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = None
    if req.project_id:
        project = await _get_user_project(req.project_id, current_user.id, db)
        
    if not project:
        # Find the most recently active project for this user
        result = await db.execute(
            select(Project)
            .where(Project.user_id == current_user.id)
            .order_by(Project.created_at.desc())
            .limit(1)
        )
        project = result.scalar_one_or_none()
        
    if not project:
        raise HTTPException(status_code=400, detail="You must create at least one project first.")

    # Create a Keyword entry for this manual keyword
    keyword_res = await db.execute(
        select(Keyword)
        .where(Keyword.project_id == project.id, Keyword.phrase == req.main_keyword)
    )
    keyword = keyword_res.scalar_one_or_none()
    
    if not keyword:
        keyword = Keyword(
            project_id=project.id,
            phrase=req.main_keyword,
            keyword_type="primary"
        )
        db.add(keyword)
        await db.flush()

    # Extract seed keywords from cluster
    seed_keywords = [k.strip() for k in req.keyword_cluster.split("\n") if k.strip()]
    if not seed_keywords:
        seed_keywords = [req.main_keyword]
    
    competitor_urls = await _fallback_project_urls(db, project.id, source_type="competitor", limit=6)
    own_urls = await _fallback_project_urls(db, project.id, source_type="own", limit=2)

    try:
        package = await run_in_threadpool(
            generate_article_package,
            project_name=project.name,
            project_domain=project.domain,
            primary_keyword=req.main_keyword,
            architecture_brief=req.architecture_brief,
            seed_keywords=seed_keywords,
            competitor_urls=competitor_urls,
            own_urls=own_urls,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    draft = ArticleDraft(
        project_id=project.id,
        keyword_id=keyword.id,
        status=package["status"],
        title=package["title"],
        content_markdown=package["content_markdown"],
        audit_score=package["audit"].get("score") if package.get("audit") else None,
        generation_attempts=package["attempts"],
        research_summary={
            "brief": package["brief"],
            "competitor_pages": package["competitor_pages"],
            "own_pages": package["own_pages"],
        },
        audit_feedback=package.get("audit"),
    )
    db.add(draft)
    await db.flush()
    await db.refresh(draft)
    return _article_out(draft, keyword.phrase)


@router.post("/{project_id}/articles/{article_id}/write-final", response_model=ArticleDraftOut)
async def write_final_article_endpoint(
    project_id: uuid.UUID,
    article_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_user_project(project_id, current_user.id, db)
    
    result = await db.execute(
        select(ArticleDraft)
        .where(ArticleDraft.id == article_id, ArticleDraft.project_id == project.id)
    )
    draft = result.scalar_one_or_none()
    if not draft:
        raise HTTPException(status_code=404, detail="Article draft not found")
        
    keyword_res = await db.execute(select(Keyword).where(Keyword.id == draft.keyword_id))
    keyword = keyword_res.scalar_one_or_none()
    if not keyword:
        raise HTTPException(status_code=404, detail="Keyword not found")

    # Set status to generating
    if draft.status == "generating":
        raise HTTPException(status_code=409, detail="Article generation is already running")
    research = dict(draft.research_summary or {})
    master_prompt = research.get("master_prompt") or draft.content_markdown
    if not master_prompt:
        raise HTTPException(status_code=400, detail="Generate an article prompt first")
    research["master_prompt"] = master_prompt
    draft.research_summary = research
    draft.status = "generating"
    await db.commit()

    try:
        package = await run_in_threadpool(
            generate_final_article_package,
            primary_keyword=keyword.phrase,
            master_prompt=master_prompt,
            brief=research.get("brief", {}),
        )
    except Exception as exc:
        draft.status = "error"
        await db.commit()
        if isinstance(exc, ValueError):
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        raise HTTPException(status_code=502, detail="Article generation failed. Please retry.") from exc

    draft.status = package["status"]
    draft.title = package["title"]
    
    # Save the original prompt into research_summary before overwriting
    research = dict(draft.research_summary) if draft.research_summary else {}
    if "master_prompt" not in research:
        research["master_prompt"] = draft.content_markdown
    draft.research_summary = research
    
    draft.content_markdown = package["content_markdown"]
    draft.audit_score = package["audit"].get("score") if package.get("audit") else None
    draft.generation_attempts = (draft.generation_attempts or 0) + package["attempts"]
    draft.audit_feedback = package.get("audit")

    await db.commit()
    await db.refresh(draft)
    return _article_out(draft, keyword.phrase)


@router.get("/{project_id}/articles", response_model=ArticleListResponse)
async def list_articles(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_user_project(project_id, current_user.id, db)
    result = await db.execute(
        select(ArticleDraft, Keyword.phrase)
        .join(Keyword, Keyword.id == ArticleDraft.keyword_id)
        .where(ArticleDraft.project_id == project_id)
        .order_by(ArticleDraft.created_at.desc())
        .limit(10)
    )
    items = [_article_out(article, keyword_phrase) for article, keyword_phrase in result.all()]
    return ArticleListResponse(items=items)


async def _get_user_project(project_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession) -> Project:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def _get_project_keyword(project_id: uuid.UUID, keyword_id: uuid.UUID, db: AsyncSession) -> Keyword:
    result = await db.execute(
        select(Keyword).where(Keyword.project_id == project_id, Keyword.id == keyword_id)
    )
    keyword = result.scalar_one_or_none()
    if not keyword:
        raise HTTPException(status_code=404, detail="Keyword not found")
    return keyword


async def _keyword_source_urls(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    keyword_id: uuid.UUID,
    source_type: str,
    limit: int,
) -> list[str]:
    result = await db.execute(
        select(Url.url)
        .join(KeywordUrl, KeywordUrl.url_id == Url.id)
        .where(
            KeywordUrl.keyword_id == keyword_id,
            Url.project_id == project_id,
            Url.source_type == source_type,
            Url.status == "scraped",
        )
        .order_by(Url.word_count.desc().nullslast(), Url.scraped_at.desc().nullslast())
        .limit(limit)
    )
    return [url for (url,) in result.all()]


async def _fallback_project_urls(
    db: AsyncSession,
    project_id: uuid.UUID,
    *,
    source_type: str,
    limit: int,
) -> list[str]:
    result = await db.execute(
        select(Url.url)
        .where(Url.project_id == project_id, Url.source_type == source_type, Url.status == "scraped")
        .order_by(Url.word_count.desc().nullslast(), Url.scraped_at.desc().nullslast())
        .limit(limit)
    )
    return [url for (url,) in result.all()]


def _article_out(article: ArticleDraft, keyword_phrase: str) -> ArticleDraftOut:
    return ArticleDraftOut(
        id=article.id,
        project_id=article.project_id,
        keyword_id=article.keyword_id,
        keyword_phrase=keyword_phrase,
        status=article.status,
        title=article.title,
        content_markdown=article.content_markdown,
        audit_score=article.audit_score,
        generation_attempts=article.generation_attempts,
        research_summary=article.research_summary,
        audit_feedback=article.audit_feedback,
        created_at=article.created_at,
        updated_at=article.updated_at,
    )
