import asyncio
from nlp.openrouter import cluster_hub_and_spoke
from dotenv import load_dotenv

load_dotenv()

async def main():
    print("Testing cluster_hub_and_spoke...")
    dummy_keywords = [
        {"phrase": "korean age calculator", "type": "keyword", "is_ai": False},
        {"phrase": "how to calculate korean age", "type": "keyword", "is_ai": False},
        {"phrase": "what is korean age", "type": "keyword", "is_ai": False},
        {"phrase": "korean age", "type": "entity", "is_ai": False}
    ]
    try:
        res = await cluster_hub_and_spoke(dummy_keywords)
        print("RESULT:")
        print(res)
    except Exception as e:
        print("EXCEPTION:", e)

if __name__ == "__main__":
    asyncio.run(main())
