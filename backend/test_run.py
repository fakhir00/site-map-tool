import sys
import logging
import uuid
from app.database import engine
from workers.pipeline import run_full_pipeline

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    job_id = "9fc0bb87-497a-46a0-9e90-99e1a6844f99"
    project_id = "a660e2ce-4acc-4f34-b88f-993bc53a1ec1"
    run_full_pipeline(project_id, job_id)
