"""Shared editorial decision rules for discovery, architecture and review."""

import re

ONE_PAGE_TEST_KEYS = ("same_user", "same_task", "same_answer", "same_serp_intent", "same_entity")

INTENT_CLUSTERING_RULES = """
Final spoke count is determined by semantic validation, distinct search intent, product capability,
and unique user value. There is no minimum or target URL count. Do not add pages just to increase coverage
counts. Reject page proposals that depend on capabilities outside the stated product/site scope.

CLUSTER BY USER INTENT, NOT WORD SIMILARITY
A semantic cluster represents one coherent user need. Shared words are not sufficient evidence.
Normalize obvious wording/order variations, but retain the original keywords as supporting phrases.
For each cluster ask: do these queries describe the same task; would one excellent page satisfy all
of them; would users expect the same content; would separate pages compete; and is there enough
unique information to make separate pages genuinely useful?
Examine free, online, easy, best, simple, web, tool and software in context. If a modifier does not
change the task or expected answer, merge. Do not blindly strip meaningful entities, constraints or
comparison intent: choosing the best products can differ from using a product.

FEATURE PAGE TEST
Whenever a keyword contains "with X", "for X", "using X", "X maker", "X diagram maker",
"X circuit maker" or "X symbol" (including plural forms), do not automatically create a page.
Classify what X represents in this context: a major independent workflow, a meaningful entity,
a distinct user task, a major feature, or a subsection/small feature/component of an existing resource.
Record that classification and its reasoning in the keyword decision reason. A meaningful entity
or major feature is not sufficient by itself: identify the independent task and unique content before
granting a URL, and still apply the one-page test. The pattern is a review trigger, not a verdict.
If X is only a small feature/component or subsection, retain the keyword as supporting content on
the appropriate parent page (feature, H2 or FAQ placement); do not publish a separate URL or discard it.
Choose the parent by the task it satisfies, not just shared words or the homepage by default.
Keep the original keyword and its useful content requirements. If a suitable parent is missing,
reconsider the architecture within the supplied inventory; do not invent a destination or approve
the small feature as a standalone page merely because its parent was omitted.

THE ONE-PAGE TEST — before creating any URL, compare it with the hub and related proposed/owned pages:
A same_user: Would essentially the same person search both queries?
B same_task: Are they trying to accomplish the same thing?
C same_answer: Would the majority of the useful content be identical?
D same_serp_intent: Would results reasonably contain the same type of pages?
E same_entity: Are both fundamentally about the same entity/topic?
If most (at least three) answers are YES, do not create another URL. Retain the keyword naturally on
the surviving page. Judge expected SERP intent conservatively; do not claim live SERPs were checked
unless actual search-result evidence is supplied. Do not infer YES just from shared words.

DOORWAY / NEAR-DUPLICATE RISK
Flag proposed pages that repeat the same task, functionality or answer while changing a feature,
component, symbol, format, audience or modifier. A feature is not automatically a standalone page.
Consolidate features within the appropriate comprehensive resource, section or tool when that page
can satisfy them. Prefer an existing suitable resource; do not invent a new keyword or URL to merge.
Keep a feature-specific page only when its independently useful task and unique content justify it.
Apply these rules to any subject; examples or vocabulary from one niche must not define the rules.
The objective is maximum useful topical coverage with minimum unnecessary duplication, not URL count.
""".strip()


def requires_feature_page_test(keyword: str) -> bool:
    """Flag phrasing for semantic assessment; never decide its URL from the match."""
    return bool(re.search(
        r"\b(?:with|for|using)\s+\S|\b\w+\s+(?:makers?|symbols?)\b",
        str(keyword or ""), re.IGNORECASE,
    ))


def one_page_test_passes(test: object) -> bool:
    """Only a complete boolean checklist is evidence, never strings or missing votes."""
    return (
        isinstance(test, dict)
        and all(type(test.get(key)) is bool for key in ONE_PAGE_TEST_KEYS)
        and sum(test[key] for key in ONE_PAGE_TEST_KEYS) >= 3
    )
