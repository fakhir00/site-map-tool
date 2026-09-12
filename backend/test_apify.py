import sys
import logging
from app.config import settings
from scraping.apify_client_module import search_google_via_apify

logging.basicConfig(level=logging.INFO)

print("Starting test...")
results = search_google_via_apify("moon nodes calculator", max_results=10)
print(f"Results: {len(results)}")
for r in results:
    print(r['url'], r['title'])
