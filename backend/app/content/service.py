import uuid
from typing import Any

from app.config import settings
from nlp.keywords import keyword_terms
from nlp.openrouter import audit_article, build_article_brief, judge_competitor_domains, write_article
from scraping.crawler import ScrapedPage, scrape_page
from workers.pipeline import (
    _is_blocked_competitor_root,
    _origin,
    _registered_domain,
    _search_google_result_urls,
)


def generate_article_package(
    *,
    project_name: str,
    project_domain: str,
    primary_keyword: str,
    seed_keywords: list[str],
    competitor_urls: list[str],
    own_urls: list[str],
) -> dict[str, Any]:
    if not settings.OPENROUTER_API_KEY:
        raise ValueError("OpenRouter API key is required to generate articles")

    competitor_pages = _collect_research_pages(competitor_urls, limit=settings.ARTICLE_RESEARCH_SOURCE_LIMIT)
    google_pages = _collect_google_research(primary_keyword, project_domain)
    own_pages = _collect_research_pages(own_urls, limit=2)

    page_lookup = {page["url"]: page for page in competitor_pages}
    for page in google_pages:
        page_lookup.setdefault(page["url"], page)
    merged_competitors = list(page_lookup.values())[: max(settings.ARTICLE_RESEARCH_SOURCE_LIMIT, 5)]

    brief = build_article_brief(
        project_name=project_name,
        target_domain=project_domain,
        primary_keyword=primary_keyword,
        seed_keywords=seed_keywords,
        competitor_pages=merged_competitors,
        own_pages=own_pages,
    )
    if not brief:
        brief = _heuristic_brief(primary_keyword, merged_competitors)

    article_markdown = ""
    audit: dict[str, Any] | None = None
    revision_notes: list[str] = []
    attempts = max(1, settings.ARTICLE_GENERATION_MAX_ATTEMPTS)

    for attempt in range(1, attempts + 1):
        article_markdown = write_article(
            project_name=project_name,
            primary_keyword=primary_keyword,
            brief=brief,
            competitor_pages=merged_competitors,
            revision_notes=revision_notes,
        )
        audit = audit_article(
            primary_keyword=primary_keyword,
            brief=brief,
            article_markdown=article_markdown,
        ) or {
            "score": 0,
            "passed": False,
            "strengths": [],
            "issues": ["The article audit did not return a valid result."],
            "revision_notes": ["Rewrite the article with stronger structure, clarity, and SEO coverage."],
        }
        score = int(audit.get("score") or 0)
        passed = bool(audit.get("passed")) or score >= 90
        audit["passed"] = passed
        audit["score"] = score
        if passed:
            return {
                "status": "passed",
                "title": _article_title(article_markdown, brief, primary_keyword),
                "content_markdown": article_markdown,
                "audit": audit,
                "brief": brief,
                "attempts": attempt,
                "competitor_pages": merged_competitors,
                "own_pages": own_pages,
            }
        revision_notes = [
            str(note).strip()
            for note in audit.get("revision_notes", [])
            if str(note).strip()
        ][:8]

    return {
        "status": "needs_revision",
        "title": _article_title(article_markdown, brief, primary_keyword),
        "content_markdown": article_markdown,
        "audit": audit,
        "brief": brief,
        "attempts": attempts,
        "competitor_pages": merged_competitors,
        "own_pages": own_pages,
    }


def _collect_google_research(primary_keyword: str, project_domain: str) -> list[dict[str, Any]]:
    own_root = _registered_domain(project_domain)
    grouped: dict[str, list[str]] = {}
    for href in _search_google_result_urls(primary_keyword, max_results=settings.GOOGLE_SERP_RESULT_LIMIT):
        origin = _origin(href)
        root = _registered_domain(origin)
        if not origin or not root or root == own_root or _is_blocked_competitor_root(root):
            continue
        grouped.setdefault(origin, [])
        grouped[origin].append(href)
        if len(grouped) >= settings.MAX_COMPETITOR_JUDGE_CANDIDATES:
            break

    candidates = [
        {"domain": domain, "sample_urls": urls[:2]}
        for domain, urls in grouped.items()
    ]
    judged = judge_competitor_domains(
        [primary_keyword],
        project_domain,
        candidates,
        max_domains=min(5, len(candidates)),
    )
    accepted = {item["domain"] for item in judged} if judged else set(grouped.keys())

    pages: list[dict[str, Any]] = []
    for domain, urls in grouped.items():
        if domain not in accepted:
            continue
        pages.extend(_collect_research_pages(urls[:1], limit=1))
    return pages


def _collect_research_pages(urls: list[str], limit: int) -> list[dict[str, Any]]:
    seen: set[str] = set()
    pages: list[dict[str, Any]] = []
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        page = scrape_page(
            url,
            delay_min=0.05,
            delay_max=0.15,
            timeout=min(settings.REQUEST_TIMEOUT, 12),
            max_retries=1,
        )
        summary = _page_summary(page)
        if summary:
            pages.append(summary)
        if len(pages) >= limit:
            break
    return pages


def _page_summary(page: ScrapedPage) -> dict[str, Any] | None:
    if page.error or page.word_count < 150 or not page.text:
        return None
    return {
        "url": page.url,
        "domain": _origin(page.url),
        "title": page.h1,
        "h2s": page.h2s[:6],
        "h3s": page.h3s[:6],
        "word_count": page.word_count,
        "readability_score": page.readability_score,
        "publish_date": page.publish_date.isoformat() if page.publish_date else None,
        "summary": _truncate(page.text, 1400),
        "keyword_terms": sorted(keyword_terms((page.h1 or "") + " " + " ".join(page.h2s[:4]), min_len=2)),
    }


def _truncate(value: str, limit: int) -> str:
    cleaned = " ".join(value.split())
    return cleaned[:limit]


def _article_title(article_markdown: str, brief: dict[str, Any], fallback_keyword: str) -> str:
    for line in article_markdown.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return str(brief.get("recommended_title") or fallback_keyword).strip()


def _heuristic_brief(primary_keyword: str, competitor_pages: list[dict[str, Any]]) -> dict[str, Any]:
    takeaways = []
    for page in competitor_pages[:4]:
        title = page.get("title") or page.get("url")
        takeaways.append(f"Cover and improve on: {title}")
    return {
        "search_intent": f"Readers want practical help with {primary_keyword}.",
        "reader_persona": f"Someone comparing options or learning {primary_keyword}.",
        "article_angle": f"A clear, practical guide to {primary_keyword}.",
        "recommended_title": primary_keyword.title(),
        "meta_description": f"Learn {primary_keyword} with a clearer, more actionable guide.",
        "content_gaps": takeaways[:4] or [f"Add fresher examples for {primary_keyword}."],
        "outline": [
            {"heading": f"What is {primary_keyword}?", "points": ["Define the topic clearly.", "Explain why it matters."]},
            {"heading": f"How to approach {primary_keyword}", "points": ["Walk through the process.", "Call out mistakes to avoid."]},
            {"heading": f"Best practices for {primary_keyword}", "points": ["Use examples.", "Add practical recommendations."]},
        ],
        "competitor_takeaways": takeaways[:4],
        "must_include_terms": sorted(keyword_terms(primary_keyword, min_len=2)),
    }
