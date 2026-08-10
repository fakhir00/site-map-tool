import sys
import uuid
import os
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from app.models import Project, ScanJob
from workers.pipeline import run_full_pipeline

# Set env vars to connect to neon db
os.environ["DATABASE_URL"] = "postgresql+asyncpg://neondb_owner:npg_GbZjg04RmHQu@ep-crimson-sun-aydl96jh.c-5.us-east-2.aws.neon.tech/neondb?ssl=require"
os.environ["SYNC_DATABASE_URL"] = "postgresql://neondb_owner:npg_GbZjg04RmHQu@ep-crimson-sun-aydl96jh.c-5.us-east-2.aws.neon.tech/neondb?sslmode=require"

engine = create_engine(os.environ["SYNC_DATABASE_URL"])
Session = sessionmaker(bind=engine)
db = Session()

# get the latest project
project = db.execute(select(Project).order_by(Project.created_at.desc()).limit(1)).scalar_one_or_none()
if not project:
    print("No project found")
    sys.exit(1)

job = db.execute(select(ScanJob).where(ScanJob.project_id == project.id).order_by(ScanJob.created_at.desc()).limit(1)).scalar_one_or_none()
if not job:
    print("No job found")
    sys.exit(1)

print(f"Running pipeline for project {project.id} job {job.id}")
try:
    run_full_pipeline(str(project.id), str(job.id))
    print("Pipeline finished!")
except Exception as e:
    print("Error:", e)
