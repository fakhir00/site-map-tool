import asyncio
from backend.nlp.openrouter import cluster_hub_and_spoke
from backend.app.database import AsyncSessionLocal
from backend.app.models import Keyword, Project
from sqlalchemy import select
from dotenv import load_dotenv

load_dotenv("backend/.env")

async def test():
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(Project).limit(1))
        p = res.scalars().first()
        if not p: return
        
        q = select(Keyword.phrase).where(Keyword.project_id == p.id).order_by(Keyword.frequency.desc())
        result = await db.execute(q)
        phrases = [row[0] for row in result.all()]
        if not phrases: return
        print(f"Clustering {len(phrases)} phrases for project {p.domain}")
        res = await cluster_hub_and_spoke(phrases)
        print("Result:", res)

asyncio.run(test())
