import uuid
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models import User, Project, ScanJob
from app.schemas import ScanJobOut, ScanProgress
from app.auth.jwt import get_current_user
from app.config import settings

router = APIRouter(prefix="/api/projects", tags=["scan"])


@router.post("/{project_id}/scan/start", response_model=ScanJobOut)
async def start_scan(
    project_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_user_project(project_id, current_user.id, db)

    if project.status == "running":
        raise HTTPException(status_code=409, detail="Scan already running for this project")
    if project.status == "paused":
        raise HTTPException(status_code=409, detail="Scan is paused. Resume it instead of starting a new scan.")

    job = ScanJob(project_id=project_id)
    db.add(job)
    await db.flush()
    project.status = "running"
    job.status = "queued"
    await db.commit()
    await db.refresh(job)

    job.celery_task_id = _dispatch_scan(background_tasks, project_id, job.id, resume_existing=False)
    await db.commit()

    return ScanJobOut.model_validate(job)


@router.get("/{project_id}/scan/status", response_model=ScanProgress)
async def scan_status(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_user_project(project_id, current_user.id, db)

    # No Redis locally - return None
    current_url = None

    percent = 0.0
    if project.urls_found > 0:
        percent = round((project.urls_processed + project.urls_failed) / project.urls_found * 100, 1)

    return ScanProgress(
        status=project.status,
        urls_found=project.urls_found,
        urls_processed=project.urls_processed,
        urls_failed=project.urls_failed,
        current_url=current_url,
        percent=min(percent, 100.0),
    )


@router.post("/{project_id}/scan/pause")
async def pause_scan(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_user_project(project_id, current_user.id, db)
    if project.status != "running":
        raise HTTPException(status_code=409, detail="Only a running scan can be paused")
    project.status = "paused"
    await db.commit()
    return {"message": "Scan paused"}


@router.post("/{project_id}/scan/resume")
async def resume_scan(
    project_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_user_project(project_id, current_user.id, db)
    if project.status != "paused":
        raise HTTPException(status_code=409, detail="Only a paused scan can be resumed")

    job = ScanJob(project_id=project_id)
    db.add(job)
    await db.flush()
    project.status = "running"
    job.status = "queued"
    await db.commit()
    await db.refresh(job)

    job.celery_task_id = _dispatch_scan(background_tasks, project_id, job.id, resume_existing=True)
    await db.commit()

    return ScanJobOut.model_validate(job)


@router.get("/{project_id}/scan/jobs", response_model=list[ScanJobOut])
async def list_scan_jobs(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_user_project(project_id, current_user.id, db)
    result = await db.execute(
        select(ScanJob)
        .where(ScanJob.project_id == project_id)
        .order_by(ScanJob.created_at.desc())
        .limit(20)
    )
    return [ScanJobOut.model_validate(j) for j in result.scalars().all()]


async def _get_user_project(project_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession) -> Project:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _dispatch_scan(
    background_tasks: BackgroundTasks,
    project_id: uuid.UUID,
    job_id: uuid.UUID,
    resume_existing: bool,
) -> str:
    if settings.USE_CELERY:
        from workers.pipeline import run_full_pipeline_task

        task = run_full_pipeline_task.delay(str(project_id), str(job_id), resume_existing)
        return task.id

    from workers.pipeline import run_full_pipeline

    background_tasks.add_task(run_full_pipeline, str(project_id), str(job_id), resume_existing)
    return "local-background-task"
