import sys
import uuid
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from app.config import settings
from app.models import Project, ScanJob

sync_engine = create_engine(
    settings.SYNC_DATABASE_URL, 
    connect_args={"check_same_thread": False} if "sqlite" in settings.SYNC_DATABASE_URL else {}
)
SyncSession = sessionmaker(bind=sync_engine, expire_on_commit=False)

def check_project():
    db = SyncSession()
    projects = db.execute(select(Project)).scalars().all()
    for p in projects:
        print(f"Project: {p.id}, Status: {p.status}, URL: {p.domain}, URL count: {p.urls_found}")

if __name__ == "__main__":
    check_project()
