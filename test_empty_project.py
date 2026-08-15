import asyncio
from backend.app.database import AsyncSessionLocal
from backend.app.models import Keyword, Project
from sqlalchemy import select

async def test():
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(Project))
        projects = res.scalars().all()
        for p in projects:
            q = select(Keyword.phrase).where(Keyword.project_id == p.id)
            result = await db.execute(q)
            phrases = [row[0] for row in result.all()]
            if len(phrases) == 0:
                print(f"Project {p.domain} has 0 keywords. ID: {p.id}")
                return

asyncio.run(test())
