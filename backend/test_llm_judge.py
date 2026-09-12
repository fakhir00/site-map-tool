import sys
import logging
from app.config import settings
from nlp.openrouter import judge_competitor_domains

logging.basicConfig(level=logging.INFO)

candidates = [
    {
        "domain": "https://astrostyle.com/",
        "sample_urls": ["https://astrostyle.com/cosmic-calculators/lunar-north-south-nodes/"],
        "queries": ["moon nodes calculator"],
        "sources": ["apify_page_1"],
        "best_rank": 1,
        "titles": ["What Are My Lunar North and South Nodes? - Astrostyle"],
        "snippets": ["Calculate moon nodes..."]
    },
    {
        "domain": "https://cafeastrology.com/",
        "sample_urls": ["https://cafeastrology.com/northnodetables.html"],
        "queries": ["moon nodes calculator"],
        "sources": ["apify_page_1"],
        "best_rank": 3,
        "titles": ["Find the Sign of Your North Node in Astrology: Tables"],
        "snippets": ["moon nodes"]
    }
]

print("Starting test...")
results = judge_competitor_domains(
    ["moon nodes calculator"],
    "moonnodescalculator.com",
    candidates,
    max_domains=25
)
print(f"Results: {results}")
