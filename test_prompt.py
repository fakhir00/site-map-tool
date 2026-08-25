import asyncio
from backend.nlp.openrouter import cluster_hub_and_spoke

async def main():
    try:
        keywords = [{"phrase": "test entity", "type": "entity", "is_ai": False}]
        res = await cluster_hub_and_spoke(keywords)
        print("Success:", res)
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(main())
