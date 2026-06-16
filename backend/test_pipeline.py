import sys
import asyncio
from app.database import engine
from app.models import Base, Project, User
from workers.pipeline import run_full_pipeline

async def test():
    async with engine.begin() as conn:
        pass

if __name__ == "__main__":
    pass
