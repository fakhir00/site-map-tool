import asyncio
from app.database import AsyncSessionLocal
from app.models import Project, Keyword, KeywordUrl, Url
from sqlalchemy import select
import uuid

async def main():
    async with AsyncSessionLocal() as db:
        # get any project
        result = await db.execute(select(Project).limit(1))
        project = result.scalar_one_or_none()
        if not project:
            print("No project found")
            return
            
        print(f"Project: {project.id} {project.name}")
        
        q_existing = (
            select(Keyword.phrase, Keyword.keyword_type, Url.source_domain)
            .outerjoin(KeywordUrl, Keyword.id == KeywordUrl.keyword_id)
            .outerjoin(Url, KeywordUrl.url_id == Url.id)
            .where(Keyword.project_id == project.id)
            .order_by(Keyword.frequency.desc())
        )
        result = await db.execute(q_existing)
        
        keyword_map = {}
        for phrase, kw_type, domain in result.all():
            if phrase not in keyword_map:
                keyword_map[phrase] = {"phrase": phrase, "type": kw_type, "is_ai": False}
            if domain == "AI Recommendations":
                keyword_map[phrase]["is_ai"] = True
                
        existing_keywords = list(keyword_map.values())
        print(f"Found {len(existing_keywords)} keywords. AI: {sum(1 for k in existing_keywords if k['is_ai'])}")
        
        from nlp.openrouter import cluster_hub_and_spoke
        clusters = await cluster_hub_and_spoke(existing_keywords)
        if clusters:
            print("Cluster succeeded!")
            print(str(clusters)[:500])
        else:
            print("Cluster failed (returned None)")

if __name__ == "__main__":
    asyncio.run(main())
