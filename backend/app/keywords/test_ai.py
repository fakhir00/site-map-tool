import asyncio
from nlp.openrouter import filter_keyword_gap_recommendations

async def main():
    candidates = ["cheap options trading", "0dte options", "0dte spy", "spy options", "day trading options"]
    rows = [{"phrase": phrase, "type": "long-tail"} for phrase in candidates]
    res = await asyncio.to_thread(filter_keyword_gap_recommendations, ["options trading"], rows)
    print("Filter Result:", res)

if __name__ == "__main__":
    asyncio.run(main())
