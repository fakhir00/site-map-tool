"""Small, bounded autocomplete research pass independent of paid search quotas.

This public endpoint can change or throttle. Validate its echoed query and shape,
stop on throttling, and treat failure as an optional-source outage. Suggestions
are observed wording, not monthly search-volume measurements.
"""
import re
from urllib.parse import urlencode

import requests

from nlp.keywords import clean_phrase, is_publishable_keyword, is_topic_relevant_keyword

ENDPOINT = "https://suggestqueries.google.com/complete/search"


def research_autocomplete(seeds, topic_terms, negative_terms, *, locale="us", language="en", limit=12, diagnostics=None):
    queries = list(dict.fromkeys([
        *(clean_phrase(seed) for seed in seeds),
        *(term.removeprefix("__research_seed__") for term in sorted(topic_terms or set()) if term.startswith("__research_seed__")),
    ]))
    queries = [query for query in queries if query and is_topic_relevant_keyword(query, seeds, topic_terms, negative_terms)][:max(0, min(12, limit))]
    rows = {}
    for query in queries:
        params = {"client": "firefox", "q": query,
                  "gl": locale if re.fullmatch(r"[a-z]{2}", locale or "") else "us",
                  "hl": language if re.fullmatch(r"[a-z]{2}", language or "") else "en"}
        try:
            response = requests.get(ENDPOINT, params=params, timeout=6)
            if response.status_code in (403, 429):
                if diagnostics is not None:
                    diagnostics.append("Autocomplete research was throttled; remaining queries were skipped.")
                break
            response.raise_for_status()
            payload = response.json()
            if (not isinstance(payload, list) or len(payload) < 2 or payload[0] != query
                    or not isinstance(payload[1], list)):
                raise ValueError("Autocomplete response did not match its query")
            for suggestion in payload[1][:20]:
                if not isinstance(suggestion, str):
                    continue
                phrase = clean_phrase(suggestion)
                if (not is_publishable_keyword(phrase, min_words=2, negative_terms=negative_terms)
                        or not is_topic_relevant_keyword(phrase, seeds, topic_terms, negative_terms)):
                    continue
                rows.setdefault(phrase, {
                    "phrase": phrase, "type": "long-tail", "search_volume": None, "difficulty": None,
                    "evidence": {"kind": "autocomplete", "query": query, "excerpt": phrase,
                                 "url": ENDPOINT + "?" + urlencode(params)},
                })
        except (requests.RequestException, ValueError, TypeError):
            if diagnostics is not None:
                diagnostics.append("Autocomplete research was unavailable or returned an invalid response.")
            # Do not multiply failing requests or send unrelated fallback data.
            break
    return list(rows.values())
