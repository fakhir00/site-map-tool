import asyncio
from backend.nlp.openrouter import cluster_hub_and_spoke
from dotenv import load_dotenv

load_dotenv("backend/.env")

async def test():
    keywords = ["advanced 0dte trading techniques", "0dte trading methods", "advanced 0dte trading tips", "vix strategies"]
    print("Testing hub and spoke...")
    res = await cluster_hub_and_spoke(keywords)
    print("Result:", res)

if __name__ == "__main__":
    asyncio.run(test())
