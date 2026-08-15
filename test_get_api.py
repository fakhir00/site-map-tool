import asyncio
from backend.app.database import AsyncSessionLocal
from backend.app.models import HubSpokeCluster
from sqlalchemy import select

async def test():
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(HubSpokeCluster).limit(1))
        c = res.scalars().first()
        if c:
            print("Type of cluster_data:", type(c.cluster_data))
            print("Content:", c.cluster_data)

asyncio.run(test())
