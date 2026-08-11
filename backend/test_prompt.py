import asyncio
from app.website_prompts.service import generate_prompt_flow

async def main():
    res = generate_prompt_flow('games wheel', 'interactive tool', [])
    print(res['prompt'])
    print("ATTEMPTS:", res['attempts'])

asyncio.run(main())
