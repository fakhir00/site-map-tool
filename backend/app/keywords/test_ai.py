import asyncio
from backend.nlp.openrouter import filter_keyword_gap_recommendations

async def test():
    candidates = ["cheap options trading", "0dte options", "0dte spy", "spy options", "day trading options"]
    res = await filter_keyword_gap_recommendations(candidates)
    print("Filter Result:", res)

asyncio.run(test())
