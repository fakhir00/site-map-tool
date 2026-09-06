"""
Celery application factory.
"""

from celery import Celery
from app.config import settings

celery_app = Celery(
    "sitemapseo",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["workers.pipeline"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_timeout=5,
    broker_transport_options={"socket_connect_timeout": 5, "socket_timeout": 5},
    task_publish_retry=False,
    task_soft_time_limit=settings.SCAN_MAX_SECONDS,
    task_time_limit=settings.SCAN_MAX_SECONDS + 30,
    task_routes={
        "workers.pipeline.run_full_pipeline": {"queue": "scrape"},
        "workers.pipeline.analyze_url": {"queue": "nlp"},
    },
    beat_schedule={},
)
