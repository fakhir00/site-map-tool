import uuid
import re
from typing import Any

from app.config import settings
from nlp.keywords import keyword_terms
from nlp.openrouter import audit_article, audit_prompt, build_article_brief, is_ai_configured, judge_competitor_domains, write_prompt, write_final_article
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
    if not is_ai_configured():
        raise ValueError("AI API key is required to generate articles. Set GROQ_API_KEY or OPENROUTER_API_KEY.")

    competitor_pages = _collect_research_pages(competitor_urls, limit=settings.ARTICLE_RESEARCH_SOURCE_LIMIT)
    google_pages = (
        []
        if len(competitor_pages) >= settings.ARTICLE_RESEARCH_SOURCE_LIMIT
        else _collect_google_research(primary_keyword, project_domain)
    )
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
    attempts = max(3, settings.ARTICLE_GENERATION_MAX_ATTEMPTS)

    for attempt in range(1, attempts + 1):
        article_markdown = write_prompt(
            project_name=project_name,
            primary_keyword=primary_keyword,
            brief=brief,
            competitor_pages=merged_competitors,
            revision_notes=revision_notes,
        )
        
        audit = audit_prompt(prompt_markdown=article_markdown) or {
            "score": 0,
            "passed": False,
            "strengths": [],
            "issues": ["The prompt audit did not return a valid result."],
            "revision_notes": ["Rewrite the prompt with all required sections and perfect formatting."],
            "missing_sections": [],
            "keyword_intent_score": 0,
            "gap_coverage_score": 0,
        }
            
        score, keyword_intent_score, gap_coverage_score, passed = _normalize_audit_result(audit)
        audit["passed"] = passed
        audit["score"] = score
        audit["keyword_intent_score"] = keyword_intent_score
        audit["gap_coverage_score"] = gap_coverage_score
        if passed:
            return {
                "status": "passed",
                "title": primary_keyword.title() + " - Prompt",
                "content_markdown": article_markdown,
                "audit": audit,
                "brief": brief,
                "attempts": attempt,
                "competitor_pages": merged_competitors,
                "own_pages": own_pages,
            }
        revision_notes = audit.get("revision_notes", []) or audit.get("issues", [])

    return {
        "status": "needs_revision",
        "title": primary_keyword.title() + " - Prompt",
        "content_markdown": article_markdown,
        "audit": audit,
        "brief": brief,
        "attempts": attempts,
        "competitor_pages": merged_competitors,
        "own_pages": own_pages,
    }


def generate_final_article_package(
    *,
    primary_keyword: str,
    master_prompt: str,
    brief: dict[str, Any],
) -> dict[str, Any]:
    if not is_ai_configured():
        raise ValueError("AI API key is required to generate articles. Set GROQ_API_KEY or OPENROUTER_API_KEY.")

    article_markdown = ""
    audit: dict[str, Any] | None = None
    revision_notes: list[str] = []
    attempts = 20  # Try up to 20 times to ensure we pass the auditor

    for attempt in range(1, attempts + 1):
        article_markdown = write_final_article(
            master_prompt=master_prompt,
            revision_notes=revision_notes,
        )
        
        local_issues = _local_article_quality_issues(article_markdown, primary_keyword)
        if local_issues:
            audit = {
                "score": 55,
                "passed": False,
                "strengths": [],
                "issues": local_issues,
                "revision_notes": _revision_notes_from_local_issues(local_issues, primary_keyword),
                "missing_sections": [],
                "keyword_intent_score": 55,
                "gap_coverage_score": 55,
            }
        else:
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
                "missing_sections": [],
                "keyword_intent_score": 0,
                "gap_coverage_score": 0,
            }
            
        score, keyword_intent_score, gap_coverage_score, passed = _normalize_audit_result(audit)
        audit["passed"] = passed
        audit["score"] = score
        audit["keyword_intent_score"] = keyword_intent_score
        audit["gap_coverage_score"] = gap_coverage_score
        
        if passed:
            return {
                "status": "passed",
                "title": _article_title(article_markdown, brief, primary_keyword),
                "content_markdown": article_markdown,
                "audit": audit,
                "attempts": attempt,
            }
        revision_notes = _revision_notes_from_audit(audit, primary_keyword, attempt, attempts)

    return {
        "status": "needs_revision",
        "title": _article_title(article_markdown, brief, primary_keyword),
        "content_markdown": article_markdown,
        "audit": audit,
        "attempts": attempts,
    }


def _normalize_audit_result(audit: dict[str, Any]) -> tuple[int, int, int, bool]:
    score = int(audit.get("score") or 0)
    keyword_intent_score = int(audit.get("keyword_intent_score") or score)
    gap_coverage_score = int(audit.get("gap_coverage_score") or score)
    passed = (
        bool(audit.get("passed"))
        and score >= 92
        and keyword_intent_score >= 90
        and gap_coverage_score >= 90
    )
    return score, keyword_intent_score, gap_coverage_score, passed


def _revision_notes_from_audit(
    audit: dict[str, Any],
    primary_keyword: str,
    attempt: int,
    attempts: int,
) -> list[str]:
    score = int(audit.get("score") or 0)
    keyword_intent_score = int(audit.get("keyword_intent_score") or score)
    gap_coverage_score = int(audit.get("gap_coverage_score") or score)
    notes = [
        (
            f"Previous draft failed audit on attempt {attempt} of {attempts}: "
            f"overall {score}, keyword intent {keyword_intent_score}, gap coverage {gap_coverage_score}."
        ),
        f"Rewrite the entire article for the exact gap keyword '{primary_keyword}' until it fully passes the audit.",
    ]

    for key, label in (
        ("issues", "Fix"),
        ("missing_sections", "Add or strengthen"),
        ("revision_notes", "Rewrite instruction"),
    ):
        for item in audit.get(key, []) or []:
            value = str(item).strip()
            if value:
                notes.append(f"{label}: {value}")

    notes.append("Do not mention the audit, revision process, scores, or internal notes in the article.")
    notes.append("Return a complete replacement draft, not a patch or explanation.")

    deduped: list[str] = []
    seen: set[str] = set()
    for note in notes:
        if note not in seen:
            deduped.append(note)
            seen.add(note)
    return deduped[:12]


def _collect_google_research(primary_keyword: str, project_domain: str) -> list[dict[str, Any]]:
    own_root = _registered_domain(project_domain)
    grouped: dict[str, list[str]] = {}
    from scraping.apify_client_module import search_google_via_apify, is_apify_configured
    
    if is_apify_configured():
        results = search_google_via_apify(primary_keyword, max_results=settings.GOOGLE_SERP_RESULT_LIMIT)
        hrefs = [res["url"] for res in results]
    else:
        hrefs = _search_google_result_urls(primary_keyword, max_results=settings.GOOGLE_SERP_RESULT_LIMIT)
        
    for href in hrefs:
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


def _local_article_quality_issues(article_markdown: str, primary_keyword: str) -> list[str]:
    content = (article_markdown or "").strip()
    lowered = content.lower()
    issues: list[str] = []
    if not content:
        return ["The writer returned an empty draft."]
    if "```" in content:
        issues.append("The article contains code fences or wrapper formatting.")
    if re.search(r"\bas an ai\b|\bi cannot\b|\bi can't\b", lowered):
        issues.append("The article contains AI meta commentary.")

    words = re.findall(r"\b[\w'-]+\b", content)
    h1_count = len(re.findall(r"^#\s+.+", content, flags=re.MULTILINE))
    h2_count = len(re.findall(r"^##\s+.+", content, flags=re.MULTILINE))
    keyword_terms = keyword_terms_for_quality(primary_keyword)
    keyword_hits = sum(1 for term in keyword_terms if term in lowered)

    if len(words) < 900:
        issues.append("The article is too thin; expand it to at least 1,100 words with practical depth and examples.")
    if h1_count != 1:
        issues.append("The article must have exactly one H1.")
    if h2_count < 5:
        issues.append("The article needs at least five useful H2 sections.")
    if keyword_terms and keyword_hits < max(1, min(2, len(keyword_terms))):
        issues.append("The article does not clearly target the primary keyword.")
    if primary_keyword.lower() not in lowered:
        issues.append("The exact primary keyword should appear naturally in the article.")
    if not re.search(r"^##\s+.*(faq|questions)", lowered, flags=re.MULTILINE):
        issues.append("The article should include an FAQ or common questions section.")
    return issues


def keyword_terms_for_quality(primary_keyword: str) -> set[str]:
    return {term.lower() for term in keyword_terms(primary_keyword, min_len=3)}


def _revision_notes_from_local_issues(issues: list[str], primary_keyword: str) -> list[str]:
    notes = [f"Rewrite for the exact gap keyword '{primary_keyword}' with stronger search-intent alignment."]
    notes.extend(issues)
    notes.append("Add concrete examples, decision criteria, pitfalls, and a useful FAQ while avoiding unsupported claims.")
    return notes[:8]


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
