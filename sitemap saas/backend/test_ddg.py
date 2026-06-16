from duckduckgo_search import DDGS

try:
    with DDGS() as ddgs:
        results = [r for r in ddgs.text("SaaS marketing", max_results=3)]
        for r in results:
            print(r['href'])
except Exception as e:
    print(f"Error: {e}")
