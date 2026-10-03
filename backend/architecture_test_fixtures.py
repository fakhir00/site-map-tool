"""Explicit model approval fixtures; not real capability or SERP evidence."""


def approved_review(payload):
    pages = payload.get("pages") or [payload["master_hub"], *payload.get("spokes", [])]
    return {"passed": True, "conflicts": [], "rejections": [], "url_assessments": [
        {"target_keyword": page["target_keyword"], "classification": "distinct_task",
         "independent_task": page.get("search_intent") or page["target_keyword"],
         "unique_value": page.get("content_brief") or "Fixture: independent answer for " + page["target_keyword"],
         "capability_basis": "Fixture: supplied site scope supports this task."}
        for page in pages
    ]}
