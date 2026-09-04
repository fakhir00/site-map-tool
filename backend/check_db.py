import asyncio
from sqlalchemy import select, func
from app.database import AsyncSessionLocal
from app.models import Url, Project

async def main():
    async with AsyncSessionLocal() as session:
        # Find project circuitdiagrammaker.com
        proj = (await session.execute(select(Project).where(Project.domain.like('%circuitdiagrammaker%')))).scalars().first()
        if not proj:
            print("Project not found")
            return
            
        print(f"Project ID: {proj.id}")
        
        # Count URLs by status
        counts = (await session.execute(
            select(Url.status, func.count(Url.id))
            .where(Url.project_id == proj.id)
            .group_by(Url.status)
        )).all()
        
        print("URL Statuses:")
        for status, count in counts:
            print(f"- {status}: {count}")

asyncio.run(main())
