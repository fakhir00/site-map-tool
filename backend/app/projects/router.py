import uuid
from typing import Optional
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models import User, Project, Url, Keyword, ScanJob
from app.schemas import ProjectCreate, ProjectOut, ProjectSourceOut, ProjectStats
from app.auth.jwt import get_current_user

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not body.target_keywords:
        raise HTTPException(status_code=422, detail="Primary keyword is required")

    patterns = body.url_filter_patterns or ["/blog/", "/news/", "/post/", "/article/", "/insights/", "/resources/"]
    project = Project(
        user_id=current_user.id,
        name=body.name,
        domain=body.domain,
        own_domain=body.own_domain or body.domain,
        scan_frequency=body.scan_frequency,
        url_filter_patterns=patterns,
        target_keywords=body.target_keywords,
    )
    db.add(project)
    await db.flush()
    await db.refresh(project)
    return ProjectOut.model_validate(project)


@router.get("", response_model=list[ProjectOut])
async def list_projects(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Project)
        .where(Project.user_id == current_user.id)
        .order_by(Project.created_at.desc())
    )
    return [ProjectOut.model_validate(p) for p in result.scalars().all()]


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_user_project(project_id, current_user.id, db)
    return ProjectOut.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_user_project(project_id, current_user.id, db)
    await db.delete(project)


@router.get("/{project_id}/stats", response_model=ProjectStats)
async def project_stats(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_user_project(project_id, current_user.id, db)

    url_counts = await db.execute(
        select(Url.status, func.count(Url.id))
        .where(Url.project_id == project_id)
        .group_by(Url.status)
    )
    status_map = {row[0]: row[1] for row in url_counts.all()}

    kw_counts = await db.execute(
        select(Keyword.keyword_type, func.count(Keyword.id))
        .where(Keyword.project_id == project_id)
        .group_by(Keyword.keyword_type)
    )
    kw_type_map = {row[0]: row[1] for row in kw_counts.all()}

    total_kw_result = await db.execute(
        select(func.count(Keyword.id)).where(Keyword.project_id == project_id)
    )

    return ProjectStats(
        total_urls=sum(status_map.values()),
        scraped_urls=status_map.get("scraped", 0),
        failed_urls=status_map.get("failed", 0),
        pending_urls=status_map.get("pending", 0),
        total_keywords=total_kw_result.scalar_one_or_none() or 0,
        unique_keyword_types=kw_type_map,
    )


@router.get("/{project_id}/urls")
async def list_urls(
    project_id: uuid.UUID,
    status_filter: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_user_project(project_id, current_user.id, db)
    q = select(Url).where(Url.project_id == project_id)
    if status_filter:
        q = q.where(Url.status == status_filter)
    q = q.order_by(Url.scraped_at.desc().nullslast()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/{project_id}/sources", response_model=list[ProjectSourceOut])
async def list_sources(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_user_project(project_id, current_user.id, db)
    result = await db.execute(
        select(Url.source_type, Url.source_domain, Url.status, Url.url)
        .where(Url.project_id == project_id)
        .order_by(Url.source_type.asc(), Url.source_domain.asc().nullslast(), Url.url.asc())
    )

    grouped: dict[tuple[str, str | None], dict[str, int | str | None]] = {}
    for source_type, source_domain, url_status, url in result.all():
        domain = source_domain or _source_origin(url)
        key = (source_type, domain)
        if key not in grouped:
            grouped[key] = {
                "source_type": source_type,
                "source_domain": domain,
                "urls_found": 0,
                "scraped_urls": 0,
                "failed_urls": 0,
                "pending_urls": 0,
            }
        grouped[key]["urls_found"] += 1
        if url_status == "scraped":
            grouped[key]["scraped_urls"] += 1
        elif url_status == "failed":
            grouped[key]["failed_urls"] += 1
        elif url_status == "pending":
            grouped[key]["pending_urls"] += 1

    sources = [
        ProjectSourceOut(**source)
        for source in grouped.values()
    ]
    return sorted(
        sources,
        key=lambda source: (
            0 if source.source_type == "own" else 1,
            source.source_domain or "",
        ),
    )


async def _get_user_project(project_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession) -> Project:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


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
