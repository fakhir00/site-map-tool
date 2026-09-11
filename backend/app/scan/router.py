import uuid
import logging
import concurrent.futures
import threading
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.database import get_db
from app.models import User, Project, ScanJob
from app.schemas import ScanJobOut, ScanProgress
from app.auth.jwt import get_current_user
from app.config import settings

router = APIRouter(prefix="/api/projects", tags=["scan"])
logger = logging.getLogger(__name__)
_LOCAL_SCAN_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="bounded-scan",
)
_LOCAL_SCAN_SLOTS = threading.BoundedSemaphore(8)


@router.post("/{project_id}/scan/start", response_model=ScanJobOut)
async def start_scan(
    project_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_user_project(project_id, current_user.id, db)
    await _expire_stalled_scan(project, db)

    if project.status == "running":
        raise HTTPException(status_code=409, detail="Scan already running for this project")

    claimed = await db.execute(update(Project).where(
        Project.id == project_id, Project.status == project.status,
    ).values(status="running"))
    if not claimed.rowcount:
        raise HTTPException(status_code=409, detail="Scan state changed. Refresh and retry.")
    job = ScanJob(project_id=project_id)
    db.add(job)
    await db.flush()
    project.status = "running"
    job.status = "queued"
    await db.commit()
    await db.refresh(job)

    await _launch_scan(background_tasks, project, job, db, resume_existing=False)

    return ScanJobOut.model_validate(job)


@router.get("/{project_id}/scan/status", response_model=ScanProgress)
async def scan_status(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_user_project(project_id, current_user.id, db)
    await _expire_stalled_scan(project, db)

    # No Redis locally - return None
    current_url = None

    percent = 0.0
    if project.urls_found > 0:
        percent = round((project.urls_processed + project.urls_failed) / project.urls_found * 100, 1)
    if project.status == "running" and percent >= 100:
        current_url = "Analyzing keyword gaps and organizing recommendations"
        percent = 95.0
    elif project.status == "complete":
        percent = 100.0

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
    await db.execute(update(ScanJob).where(
        ScanJob.project_id == project_id, ScanJob.status.in_(["queued", "running"]),
    ).values(status="paused", finished_at=datetime.now(timezone.utc)))
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

    claimed = await db.execute(update(Project).where(
        Project.id == project_id, Project.status == "paused",
    ).values(status="running"))
    if not claimed.rowcount:
        raise HTTPException(status_code=409, detail="Scan state changed. Refresh and retry.")
    job = ScanJob(project_id=project_id)
    db.add(job)
    await db.flush()
    project.status = "running"
    job.status = "queued"
    await db.commit()
    await db.refresh(job)

    await _launch_scan(background_tasks, project, job, db, resume_existing=True)

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


async def _expire_stalled_scan(project: Project, db: AsyncSession) -> None:
    if project.status != "running":
        return
    result = await db.execute(select(ScanJob).where(
        ScanJob.project_id == project.id,
    ).order_by(ScanJob.created_at.desc()).limit(1))
    job = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    started = (job.started_at or job.created_at) if job else None
    if started and started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)

    if not (job and job.status in {"queued", "running"} and started and now - started < timedelta(seconds=settings.SCAN_MAX_SECONDS)):
        project.status = "error"
        if job and job.status in {"queued", "running"}:
            job.status = "error"
            job.finished_at = now
            job.error_message = "Scan stopped responding or exceeded its time limit. Start a new scan to retry."
        await db.commit()
        return

    # Detect in-process worker that died due to container restart or crash (within timeout)
    if not settings.USE_CELERY and job and job.status in {"queued", "running"}:
        try:
            from workers.pipeline import is_scan_worker_alive
            if started and (now - started).total_seconds() > 5 and not is_scan_worker_alive(job.id):
                logger.warning("Detected dead scan job %s for project %s (container restarted)", job.id, project.id)
                project.status = "paused"
                job.status = "paused"
                job.finished_at = now
                job.error_message = "Scan was interrupted by a server restart. Click Resume to continue."
                await db.commit()
                return
        except Exception as err:
            logger.debug("Active worker check failed: %s", err)


async def _launch_scan(background_tasks, project, job, db, *, resume_existing):
    try:
        job.celery_task_id = _dispatch_scan(background_tasks, project.id, job.id, resume_existing)
        await db.commit()
    except Exception as exc:
        logger.exception("Failed to dispatch scan %s", job.id)
        await db.rollback()
        project.status = "paused" if resume_existing else "error"
        job.status = "error"
        job.finished_at = datetime.now(timezone.utc)
        job.error_message = "Could not start the scan worker. Check the worker connection and retry."
        await db.commit()
        raise HTTPException(status_code=503, detail=job.error_message) from exc


def _dispatch_scan(
    background_tasks: BackgroundTasks,
    project_id: uuid.UUID,
    job_id: uuid.UUID,
    resume_existing: bool,
) -> str:
    if settings.USE_CELERY:
        from workers.pipeline import run_full_pipeline_task

        task = run_full_pipeline_task.apply_async(
            args=[str(project_id), str(job_id), resume_existing], retry=False,
        )
        return task.id

    from workers.pipeline import run_full_pipeline, ACTIVE_SCANS

    # SQLite test/local runs retain Starlette's deterministic BackgroundTasks
    # behavior. Hosted Postgres runs use one bounded worker so simultaneous scan
    # requests cannot occupy dozens of web-server threads and exhaust memory.
    if "sqlite" not in settings.DATABASE_URL:
        if not _LOCAL_SCAN_SLOTS.acquire(blocking=False):
            raise RuntimeError("The scan queue is full; retry after an active scan finishes.")
        ACTIVE_SCANS.add(job_id)
        try:
            future = _LOCAL_SCAN_EXECUTOR.submit(
                run_full_pipeline, str(project_id), str(job_id), resume_existing,
            )
        except Exception:
            ACTIVE_SCANS.discard(job_id)
            _LOCAL_SCAN_SLOTS.release()
            raise
        future.add_done_callback(lambda _future: _LOCAL_SCAN_SLOTS.release())
        return f"local-bounded-{job_id}"

    ACTIVE_SCANS.add(job_id)
    background_tasks.add_task(run_full_pipeline, str(project_id), str(job_id), resume_existing)
    return "local-background-task"
