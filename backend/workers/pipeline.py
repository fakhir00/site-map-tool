"""
Full scan workflow:
discover competitor domains from the main keyword, crawl own and competitor
sitemaps, extract keywords, and persist only competitor keyword gaps.
"""

import logging
import base64
import re
import uuid
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)

sync_engine = create_engine(
    settings.SYNC_DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 15}
    if "sqlite" in settings.SYNC_DATABASE_URL
    else {},
)
SyncSession = sessionmaker(bind=sync_engine, expire_on_commit=False)


def get_db() -> Session:
    return SyncSession()


def run_full_pipeline(project_id: str, scan_job_id: str, resume_existing: bool = False) -> None:
    """
    Run a scan. Fresh scans clear old URL/keyword results; resumed scans continue
    pending URL rows from the previous paused run.
    """
    from app.models import Keyword, KeywordUrl, Project, ScanJob, Url
    from scraping.filters import filter_blog_urls
    from scraping.sitemap import extract_all_urls_from_domain

    project_uuid = uuid.UUID(project_id)
    job_uuid = uuid.UUID(scan_job_id)
    db = get_db()

    try:
        project = db.execute(select(Project).where(Project.id == project_uuid)).scalar_one_or_none()
        job = db.execute(select(ScanJob).where(ScanJob.id == job_uuid)).scalar_one_or_none()
        if not project or not job:
            logger.error("[%s] Project or scan job not found", project_id)
            return

        _mark_running(db, project, job)
        logger.info("[%s] Starting scan for %s", project_id, project.domain)
        seed_keywords = _clean_seed_keywords(project.target_keywords)
        topic_terms = _topic_terms(seed_keywords)

        if resume_existing:
            pending_urls = _pending_urls(db, project_uuid)
            if not pending_urls:
                _sync_project_counts(db, project)
                _mark_complete(db, project, job, "complete")
                return
        else:
            _clear_previous_results(db, project_uuid)
            own_domain = _origin(project.own_domain or project.domain) or project.domain
            competitor_domains = _discover_competitor_domains(project, seed_keywords)
            required_terms = _search_required_terms(seed_keywords)
            ranking_terms = _search_ranking_terms(seed_keywords)
            per_domain_url_limit = max(1, settings.MAX_URLS_PER_SCAN // max(1, len(competitor_domains) + 1))
            logger.info("[%s] Own domain: %s", project_id, own_domain)
            logger.info("[%s] Competitor domains: %s", project_id, competitor_domains)

            project.urls_found = 0
            project.urls_processed = 0
            project.urls_failed = 0
            project.total_keywords = 0
            project.status = "running"
            db.commit()

            own_urls = _discover_content_urls(
                own_domain,
                project.url_filter_patterns,
                extract_all_urls_from_domain,
                filter_blog_urls,
                per_domain_url_limit,
                required_terms,
                ranking_terms,
                include_homepage=True,
            )
            _queue_discovered_urls(
                db,
                project,
                project_uuid,
                job_uuid,
                [(url, "own", own_domain) for url in own_urls],
            )

            for competitor_domain in competitor_domains:
                domain_urls = _discover_content_urls(
                    competitor_domain,
                    project.url_filter_patterns,
                    extract_all_urls_from_domain,
                    filter_blog_urls,
                    per_domain_url_limit,
                    required_terms,
                    ranking_terms,
                )
                _queue_discovered_urls(
                    db,
                    project,
                    project_uuid,
                    job_uuid,
                    [(url, "competitor", competitor_domain) for url in domain_urls],
                )

            logger.info("[%s] Queued %s URLs", project_id, project.urls_found)

            if not project.urls_found:
                _mark_complete(db, project, job, "complete")
                return

            pending_urls = _pending_urls(db, project_uuid)

        own_keyword_phrases: set[str] = _own_sitemap_keyword_phrases(db, project_uuid, topic_terms)
        kw_accumulator: dict[str, dict[str, Any]] = {}

        for index, url_row in enumerate(pending_urls, start=1):
            db.refresh(project)
            if project.status == "paused":
                logger.info("[%s] Scan paused after %s URLs", project_id, index - 1)
                _mark_complete(db, project, job, "paused")
                return

            logger.info("[%s] Analyzing sitemap URL %s/%s: %s", project_id, index, len(pending_urls), url_row.url)
            url_row.status = "scraped"
            url_row.error_reason = None
            url_row.h1 = _url_display_title(url_row.url)
            url_row.word_count = len(_url_words(url_row.url))
            url_row.readability_score = 0.0
            url_row.publish_date = None
            url_row.scraped_at = datetime.utcnow()
            project.urls_processed += 1
            db.commit()

            if url_row.source_type != "own":
                _collect_sitemap_keywords(kw_accumulator, url_row.url, url_row.id, topic_terms)

        _remove_covered_keywords(kw_accumulator, own_keyword_phrases)
        kw_accumulator = _refine_keyword_gap_recommendations(
            db,
            project_uuid,
            seed_keywords,
            kw_accumulator,
            topic_terms,
        )
        logger.info("[%s] Storing %s keyword gaps", project_id, len(kw_accumulator))
        _store_keywords(db, project_uuid, kw_accumulator)
        _sync_project_counts(db, project)
        _mark_complete(db, project, job, "complete")
        logger.info("[%s] Scan complete with %s keywords", project_id, project.total_keywords)

    except Exception as exc:
        logger.error("[%s] Pipeline error: %s", project_id, exc, exc_info=True)
        db.rollback()
        project = db.execute(select(Project).where(Project.id == project_uuid)).scalar_one_or_none()
        job = db.execute(select(ScanJob).where(ScanJob.id == job_uuid)).scalar_one_or_none()
        _mark_complete(db, project, job, "error", str(exc)[:500])
    finally:
        db.close()


def _discover_content_urls(
    domain: str,
    patterns: list[str] | None,
    extract_all_urls_from_domain: Any,
    filter_blog_urls: Any,
    limit: int,
    required_terms: set[str] | None = None,
    ranking_terms: set[str] | None = None,
    include_homepage: bool = False,
) -> list[str]:
    max_raw_urls = min(1000, max(limit * 10, limit + 25))
    all_urls = extract_all_urls_from_domain(
        domain,
        timeout=settings.REQUEST_TIMEOUT,
        max_urls=max_raw_urls,
    )
    logger.info("Found %s sitemap URLs for %s", len(all_urls), domain)
    content_urls = filter_blog_urls(
        all_urls,
        patterns=patterns,
        domain=domain,
    )
    relevant_urls = [url for url in all_urls if _is_relevant_content_url(url, required_terms or set())]
    relevant_urls.sort(key=lambda url: _url_relevance_score(url, ranking_terms or set()), reverse=True)
    if relevant_urls:
        content_urls = relevant_urls
    if include_homepage:
        homepage = _origin(domain)
        if homepage:
            content_urls = [homepage, *content_urls]
    if not content_urls and all_urls:
        homepage = _origin(domain)
        content_urls = [homepage] if homepage else []
    content_urls = _dedupe_localized_urls(content_urls)
    return list(dict.fromkeys(content_urls))[:limit]


def _dedupe_localized_urls(urls: list[str]) -> list[str]:
    seen_keys: set[str] = set()
    deduped: list[str] = []
    for url in urls:
        key = _localized_content_key(url)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(url)
    return deduped


def _localized_content_key(url: str) -> str:
    parsed = urlparse(url)
    segments = [segment for segment in parsed.path.strip("/").split("/") if segment]
    if segments and re.fullmatch(r"[a-z]{2}(-[a-z]{2})?", segments[0].lower()):
        segments = segments[1:]
    return "/" + "/".join(segments)


def _queue_discovered_urls(
    db: Session,
    project: Any,
    project_id: uuid.UUID,
    job_id: uuid.UUID,
    urls: list[tuple[str, str, str | None]],
) -> None:
    queued = 0
    seen: set[str] = set()
    for url, source_type, source_domain in urls:
        if url in seen:
            continue
        seen.add(url)
        _queue_url(
            db,
            project_id,
            job_id,
            url,
            source_type=source_type,
            source_domain=source_domain,
        )
        queued += 1
    if queued:
        db.commit()
        _sync_project_counts(db, project)


def _discover_competitor_domains(project: Any, seed_keywords: list[str]) -> list[str]:
    if not seed_keywords:
        logger.warning("No primary keyword provided, competitor discovery skipped")
        return []

    own_root = _registered_domain(project.own_domain or project.domain)
    required_terms = _search_required_terms(seed_keywords)
    competitor_limit = max(10, settings.MAX_COMPETITOR_DOMAINS)
    competitor_domains: list[str] = []
    competitor_roots: set[str] = set()

    def add_domain(url: str | None, require_relevance: bool = True) -> None:
        unwrapped_url = _unwrap_result_url(url)
        if require_relevance and not _is_relevant_result_url(unwrapped_url, required_terms):
            return
        domain = _origin(unwrapped_url)
        root = _registered_domain(domain)
        if not domain or not root:
            return
        if root == own_root or _is_blocked_competitor_root(root):
            return
        if root not in competitor_roots:
            competitor_domains.append(domain)
            competitor_roots.add(root)

    primary_query = _primary_competitor_search_query(seed_keywords)
    for href in _search_google_result_urls(primary_query, max_results=settings.GOOGLE_SERP_RESULT_LIMIT):
        add_domain(href, require_relevance=False)
        if len(competitor_domains) >= competitor_limit:
            return competitor_domains[:competitor_limit]

    for query in _competitor_search_queries(seed_keywords):
        for href in _search_result_urls(query, include_google=True):
            add_domain(href)
            if len(competitor_domains) >= competitor_limit:
                return competitor_domains[:competitor_limit]

    for domain in _fallback_competitor_domains(seed_keywords):
        add_domain(domain, require_relevance=False)
        if len(competitor_domains) >= competitor_limit:
            break

    return competitor_domains[:competitor_limit]


def _primary_competitor_search_query(seed_keywords: list[str]) -> str:
    return " ".join(seed_keywords[:4]).strip()


def _fallback_competitor_domains(seed_keywords: list[str]) -> list[str]:
    topic_terms = _topic_terms(seed_keywords)
    if {"circuit", "diagram"} & topic_terms or {"schematic", "electronics"} & topic_terms:
        return [
            "https://www.smartdraw.com",
            "https://www.lucidchart.com",
            "https://www.edrawsoft.com",
            "https://www.visual-paradigm.com",
            "https://www.circuit-diagram.org",
        ]
    if "wheel" in topic_terms or {"picker", "spinner"} & topic_terms:
        return [
            "https://pickerwheel.com",
            "https://spinthewheel.app",
            "https://pickeronlinewheel.com",
            "https://wheelofnames.com",
        ]
    return []


def _search_result_urls(query: str, include_google: bool = False) -> list[str]:
    urls: list[str] = []

    if include_google:
        urls.extend(_search_google_result_urls(query, max_results=settings.GOOGLE_SERP_RESULT_LIMIT))
    urls.extend(_search_bing_result_urls(query))
    urls.extend(_search_duckduckgo_html_urls(query))
    return list(dict.fromkeys(urls))


def _competitor_search_queries(seed_keywords: list[str]) -> list[str]:
    base = " ".join(seed_keywords[:4]).strip()
    queries = [
        f'"{base}" tool',
        f'"{base}" software',
        f'"{base}" generator',
        f'"{base}" maker',
        f'"{base}" alternative',
        f'"{base}" competitor',
        f'"{base}" online',
        f'"{base}"',
        f'{base} online',
        f'{base} tool',
    ]
    if " and " in base:
        rewritten = base.replace(" and ", " or ")
        queries.extend([
            f'"{rewritten}"',
            f'"{rewritten}" online',
            f'{rewritten} tool',
        ])
    base_terms = set(base.replace("-", " ").split())
    if "wheel" in base_terms and {"yes", "no"}.issubset(base_terms):
        queries = [
            "yes no picker wheel",
            "yes or no picker wheel",
            "yes no decision wheel",
            "yes or no spinner wheel",
            *queries,
        ]
    return list(dict.fromkeys(query for query in queries if query.strip()))


def _search_required_terms(seed_keywords: list[str]) -> set[str]:
    terms: set[str] = set()
    for keyword in seed_keywords:
        for term in keyword.lower().replace("-", " ").split():
            term = "".join(char for char in term if char.isalnum())
            if len(term) >= 4:
                terms.add(term)
    return terms


def _search_ranking_terms(seed_keywords: list[str]) -> set[str]:
    ignored = {"and", "or", "the", "for", "with", "near", "best"}
    terms: set[str] = set()
    for keyword in seed_keywords:
        for term in keyword.lower().replace("-", " ").split():
            term = "".join(char for char in term if char.isalnum())
            if len(term) >= 2 and term not in ignored:
                terms.add(term)
    return terms


def _url_relevance_score(url: str, ranking_terms: set[str]) -> int:
    lowered = urlparse(url).path.lower()
    return sum(1 for term in ranking_terms if term in lowered)


def _is_relevant_result_url(url: str | None, required_terms: set[str]) -> bool:
    if not url or not required_terms:
        return True
    parsed = urlparse(url)
    lowered = unquote(f"{parsed.netloc} {parsed.path}").lower()
    matched_terms = {term for term in required_terms if term in lowered}
    required_matches = 1 if len(required_terms) <= 2 else 2
    return len(matched_terms) >= required_matches


def _is_relevant_content_url(url: str, required_terms: set[str]) -> bool:
    if not required_terms:
        return True
    lowered = urlparse(url).path.lower()
    return any(term in lowered for term in required_terms)


def _search_google_result_urls(query: str, max_results: int = 10) -> list[str]:
    try:
        import requests
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        response = requests.get(
            "https://www.google.com/search",
            params={
                "q": query,
                "num": max(10, max_results),
                "hl": "en",
                "pws": "0",
            },
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.8",
            },
            timeout=settings.REQUEST_TIMEOUT,
            verify=False,
        )
        if response.status_code >= 400:
            logger.info("Google search returned HTTP %s for %r", response.status_code, query)
            return []
        return _extract_google_result_urls(response.text, max_results=max_results)
    except Exception as exc:
        logger.info("Google search failed for %r: %s", query, exc)
        return []


def _extract_google_result_urls(html: str, max_results: int = 10) -> list[str]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    candidates: list[str] = []
    containers = soup.select("div.g, div.MjjYud, div[data-sokoban-container]")
    for container in containers:
        link = container.select_one("a[href]")
        if link:
            candidates.append(link.get("href", ""))

    if len(candidates) < max_results:
        search_root = soup.select_one("#search") or soup
        candidates.extend(link.get("href", "") for link in search_root.select("a[href]"))

    urls: list[str] = []
    for href in candidates:
        normalized = _normalize_google_href(href)
        if not normalized:
            continue
        root = _registered_domain(normalized)
        if not root or _is_blocked_search_result_root(root):
            continue
        if normalized not in urls:
            urls.append(normalized)
        if len(urls) >= max_results:
            break
    return urls


def _normalize_google_href(href: str | None) -> str | None:
    if not href:
        return None
    value = href.strip()
    if value.startswith("/url?"):
        value = f"https://www.google.com{value}"
    unwrapped = _unwrap_result_url(value)
    if not unwrapped:
        return None
    parsed = urlparse(unwrapped)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    if parsed.netloc.endswith("google.com") or parsed.path.startswith(("/search", "/preferences")):
        return None
    return unwrapped


def _is_blocked_search_result_root(root: str) -> bool:
    return _is_blocked_competitor_root(root) or root in {
        "accounts.google.com",
        "maps.google.com",
        "support.google.com",
        "webcache.googleusercontent.com",
    }


def _search_bing_result_urls(query: str) -> list[str]:
    try:
        import requests
        import urllib3
        from bs4 import BeautifulSoup

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        response = requests.get(
            "https://www.bing.com/search",
            params={"q": query},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=settings.REQUEST_TIMEOUT,
            verify=False,
        )
        if response.status_code >= 400:
            return []
        soup = BeautifulSoup(response.text, "html.parser")
        return [link.get("href", "") for link in soup.select("li.b_algo h2 a") if link.get("href")]
    except Exception as exc:
        logger.info("Bing search failed for %r: %s", query, exc)
        return []


def _search_duckduckgo_html_urls(query: str) -> list[str]:
    try:
        import requests
        import urllib3
        from bs4 import BeautifulSoup

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        response = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=settings.REQUEST_TIMEOUT,
            verify=False,
        )
        if response.status_code >= 400:
            return []
        soup = BeautifulSoup(response.text, "html.parser")
        return [link.get("href", "") for link in soup.select("a.result__a") if link.get("href")]
    except Exception as exc:
        logger.info("DuckDuckGo HTML search failed for %r: %s", query, exc)
        return []


def _clean_seed_keywords(raw_keywords: list[str] | None) -> list[str]:
    if not raw_keywords:
        return []
    from nlp.keywords import clean_phrase, is_valid_keyword

    cleaned_keywords: list[str] = []
    for keyword in raw_keywords:
        cleaned = clean_phrase(keyword)
        for candidate in _expand_seed_keyword(cleaned):
            if is_valid_keyword(candidate, min_words=1) and candidate not in cleaned_keywords:
                cleaned_keywords.append(candidate)
    return cleaned_keywords


COMPOUND_KEYWORD_PARTS = [
    "schematic",
    "diagram",
    "circuit",
    "generator",
    "picker",
    "spinner",
    "random",
    "maker",
    "wheel",
    "logic",
    "gate",
    "truth",
    "table",
    "breadboard",
    "sitemap",
    "keyword",
    "and",
    "yes",
    "no",
    "seo",
]


def _expand_seed_keyword(keyword: str) -> list[str]:
    if " " in keyword or "-" in keyword:
        return [keyword]
    split_words = _split_compound_keyword(keyword)
    if len(split_words) <= 1:
        return [keyword]
    expanded = " ".join(word for word in split_words if word != "and")
    return [expanded, keyword] if expanded != keyword else [keyword]


def _split_compound_keyword(keyword: str) -> list[str]:
    words: list[str] = []
    index = 0
    while index < len(keyword):
        match = ""
        for part in COMPOUND_KEYWORD_PARTS:
            if keyword.startswith(part, index) and len(part) > len(match):
                match = part
        if match:
            words.append(match)
            index += len(match)
        else:
            index += 1
    return words


def _origin(url: str | None) -> str | None:
    if not url:
        return None
    url = url.strip().rstrip("/")
    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def _registered_domain(url: str | None) -> str | None:
    origin = _origin(url)
    if not origin:
        return None
    host = urlparse(origin).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    try:
        import tldextract

        extracted = tldextract.extract(host)
        if extracted.domain and extracted.suffix:
            return f"{extracted.domain}.{extracted.suffix}"
    except Exception:
        pass
    return host


def _unwrap_result_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.netloc.endswith("duckduckgo.com"):
        wrapped = parse_qs(parsed.query).get("uddg")
        if wrapped:
            return wrapped[0]
    if parsed.netloc.endswith("bing.com"):
        wrapped = parse_qs(parsed.query).get("u")
        if wrapped:
            value = wrapped[0]
            if value.startswith("a1"):
                encoded = value[2:]
                encoded += "=" * (-len(encoded) % 4)
                try:
                    return base64.urlsafe_b64decode(encoded).decode("utf-8", errors="ignore")
                except Exception:
                    return url
            return value
    if parsed.netloc.endswith("google.com") and parsed.path in {"/url", "/interstitial"}:
        query = parse_qs(parsed.query)
        wrapped = query.get("q") or query.get("url")
        if wrapped:
            return wrapped[0]
    return url


def _is_blocked_competitor_root(root: str) -> bool:
    blocked_roots = {
        "amazon.com",
        "apple.com",
        "britannica.com",
        "cambridge.org",
        "collinsdictionary.com",
        "colorado.edu",
        "dictionary.com",
        "duckduckgo.com",
        "facebook.com",
        "github.com",
        "google.com",
        "instagram.com",
        "linkedin.com",
        "longdo.com",
        "merriam-webster.com",
        "microsoft.com",
        "pinterest.com",
        "soundcloud.com",
        "reddit.com",
        "tiktok.com",
        "wikipedia.org",
        "x.com",
        "yahoo.com",
        "youtube.com",
    }
    return root in blocked_roots


def _mark_running(db: Session, project: Any, job: Any) -> None:
    now = datetime.utcnow()
    project.status = "running"
    job.status = "running"
    job.started_at = job.started_at or now
    job.error_message = None
    db.commit()


def _mark_complete(db: Session, project: Any, job: Any, status: str, error_msg: str | None = None) -> None:
    now = datetime.utcnow()
    if project:
        project.status = status
        if status in {"complete", "error"}:
            project.last_scanned_at = now
    if job:
        job.status = status
        if status in {"complete", "error", "paused"}:
            job.finished_at = now
        if error_msg:
            job.error_message = error_msg
    try:
        db.commit()
    except Exception:
        db.rollback()


def _clear_previous_results(db: Session, project_id: uuid.UUID) -> None:
    from app.models import Keyword, KeywordBank, KeywordUrl, Url

    keyword_ids = select(Keyword.id).where(Keyword.project_id == project_id)
    url_ids = select(Url.id).where(Url.project_id == project_id)
    db.execute(delete(KeywordBank).where(KeywordBank.keyword_id.in_(keyword_ids)))
    db.execute(delete(KeywordUrl).where(KeywordUrl.keyword_id.in_(keyword_ids)))
    db.execute(delete(KeywordUrl).where(KeywordUrl.url_id.in_(url_ids)))
    db.execute(delete(Keyword).where(Keyword.project_id == project_id))
    db.execute(delete(Url).where(Url.project_id == project_id))
    db.commit()


def _queue_url(
    db: Session,
    project_id: uuid.UUID,
    job_id: uuid.UUID,
    url: str,
    source_type: str,
    source_domain: str | None,
) -> None:
    from app.models import Url

    existing = db.execute(
        select(Url).where(Url.project_id == project_id, Url.url == url)
    ).scalar_one_or_none()
    if existing:
        existing.scan_job_id = job_id
        existing.source_type = source_type
        existing.source_domain = source_domain
        existing.status = "pending"
        existing.error_reason = None
        return

    db.add(
        Url(
            project_id=project_id,
            scan_job_id=job_id,
            url=url,
            source_type=source_type,
            source_domain=source_domain,
            status="pending",
        )
    )


def _pending_urls(db: Session, project_id: uuid.UUID) -> list[Any]:
    from app.models import Url

    return db.execute(
        select(Url)
        .where(Url.project_id == project_id, Url.status == "pending")
        .order_by(Url.source_type.desc(), Url.url.asc())
    ).scalars().all()


def _keyword_phrases(keyword_result: Any, min_words: int) -> set[str]:
    from nlp.keywords import clean_phrase, is_valid_keyword

    phrases: set[str] = set()

    def add(phrase: str) -> None:
        cleaned = clean_phrase(phrase)
        if is_valid_keyword(cleaned, min_words=min_words):
            phrases.add(cleaned)

    for phrase, _score in keyword_result.primary:
        add(phrase)
    for phrase, _score in keyword_result.lsi:
        add(phrase)
    for phrase, _entity_type in keyword_result.entities:
        add(phrase)
    for phrase in keyword_result.heading_keywords:
        add(phrase)

    return phrases


def _topic_terms(seed_keywords: list[str]) -> set[str]:
    from nlp.keywords import seed_keyword_terms

    terms = seed_keyword_terms(seed_keywords)
    expansions = {
        "circuit": {"circuits", "electrical", "electronics", "schematic", "schematics", "wiring"},
        "diagram": {"diagrams", "drawing", "drawings", "schematic", "schematics"},
        "maker": {"builder", "creator", "editor", "generator", "software", "tool", "tools"},
        "wheel": {"picker", "random", "spinner", "spin"},
        "yes": {"no", "picker", "random", "spinner"},
        "no": {"yes", "picker", "random", "spinner"},
    }
    expanded = set(terms)
    for term in terms:
        expanded.update(expansions.get(term, set()))
    return expanded


def _own_sitemap_keyword_phrases(
    db: Session,
    project_id: uuid.UUID,
    topic_terms: set[str] | None,
) -> set[str]:
    from app.models import Url

    rows = db.execute(
        select(Url.url).where(Url.project_id == project_id, Url.source_type == "own")
    ).all()
    phrases: set[str] = set()
    for (url,) in rows:
        phrases.update(_url_keyword_candidates(url, topic_terms, include_single_terms=True))
    return phrases


URL_STOPWORDS = {
    "a", "an", "and", "app", "apps", "article", "blog", "blogs", "category",
    "create", "dictionary", "en", "english", "for", "free", "guide", "guides",
    "home", "how", "html", "index", "learn", "new", "news",
    "online", "page", "pages", "php", "post", "posts", "resource", "resources",
    "the", "to", "tool", "tools", "using", "what", "why", "www",
}


def _url_words(url: str) -> list[str]:
    parsed = urlparse(url)
    path = unquote(parsed.path.lower())
    path = re.sub(r"\.(html?|php|aspx?)$", "", path)
    raw_parts = re.split(r"[/_\-+.\s]+", path)
    words: list[str] = []
    for part in raw_parts:
        part = re.sub(r"[^a-z0-9]", "", part)
        if not part or part in URL_STOPWORDS:
            continue
        if part.isdigit() or re.fullmatch(r"(19|20)\d{2}", part):
            continue
        if len(part) <= 2 and part not in {"ai", "ui", "ux", "3d"}:
            continue
        words.append(part)
    return words


def _url_keyword_candidates(
    url: str,
    topic_terms: set[str] | None,
    include_single_terms: bool = False,
) -> set[str]:
    from nlp.keywords import clean_phrase, is_publishable_keyword, is_valid_keyword

    words = _url_words(url)
    candidates: set[str] = set()
    if include_single_terms:
        for word in words:
            if is_valid_keyword(word, min_words=1):
                candidates.add(word)

    max_ngram = min(4, len(words))
    for size in range(max_ngram, 1, -1):
        for index in range(0, len(words) - size + 1):
            phrase = clean_phrase(" ".join(words[index:index + size]))
            if is_publishable_keyword(phrase, min_words=2, topic_terms=topic_terms):
                candidates.add(phrase)

    return candidates


def _url_display_title(url: str) -> str:
    words = _url_words(url)
    if not words:
        host = urlparse(url).netloc.replace("www.", "")
        return host or url
    return " ".join(words[-6:]).title()


def _collect_sitemap_keywords(
    accumulator: dict[str, dict[str, Any]],
    url: str,
    url_id: uuid.UUID,
    topic_terms: set[str] | None,
) -> None:
    for phrase in _url_keyword_candidates(url, topic_terms, include_single_terms=False):
        if phrase not in accumulator:
            accumulator[phrase] = {
                "type": "primary",
                "count": 0,
                "url_ids": set(),
                "score": 1.0,
                "source": "sitemap",
            }
        accumulator[phrase]["count"] += 1
        accumulator[phrase]["url_ids"].add(url_id)


def _collect_keywords(
    accumulator: dict[str, dict[str, Any]],
    keyword_result: Any,
    url_id: uuid.UUID,
    topic_terms: set[str] | None = None,
) -> None:
    from nlp.keywords import clean_phrase, is_publishable_keyword

    def add_keyword(phrase: str, keyword_type: str, score: float = 1.0) -> None:
        key = clean_phrase(phrase)
        if not is_publishable_keyword(key, min_words=2, topic_terms=topic_terms):
            return
        if key not in accumulator:
            accumulator[key] = {"type": keyword_type, "count": 0, "url_ids": set(), "score": score}
        accumulator[key]["count"] += 1
        accumulator[key]["url_ids"].add(url_id)

    for phrase in keyword_result.heading_keywords:
        add_keyword(phrase, "heading")
    for phrase, _entity_type in keyword_result.entities:
        add_keyword(phrase, "entity")
    for phrase, score in keyword_result.primary:
        add_keyword(phrase, "primary", score)
    for phrase, score in keyword_result.lsi:
        add_keyword(phrase, "lsi", score)


def _remove_covered_keywords(accumulator: dict[str, dict[str, Any]], own_keyword_phrases: set[str]) -> None:
    if not own_keyword_phrases:
        return

    own_term_sets = [_phrase_terms(phrase) for phrase in own_keyword_phrases]
    own_term_sets = [terms for terms in own_term_sets if terms]

    for phrase in list(accumulator.keys()):
        if phrase in own_keyword_phrases:
            del accumulator[phrase]
            continue

        phrase_terms = _phrase_terms(phrase)
        if phrase_terms and any(phrase_terms.issubset(own_terms) for own_terms in own_term_sets):
            del accumulator[phrase]


def _phrase_terms(phrase: str) -> set[str]:
    from nlp.keywords import STOPWORDS

    return {word for word in phrase.split() if word not in STOPWORDS and len(word) > 2}


def _refine_keyword_gap_recommendations(
    db: Session,
    project_id: uuid.UUID,
    seed_keywords: list[str],
    accumulator: dict[str, dict[str, Any]],
    topic_terms: set[str] | None,
) -> dict[str, dict[str, Any]]:
    if not accumulator:
        return accumulator

    candidate_rows = _keyword_gap_candidate_rows(db, project_id, accumulator, topic_terms)
    if not candidate_rows:
        return {}

    try:
        from nlp.openrouter import filter_keyword_gap_recommendations

        ai_recommendations = filter_keyword_gap_recommendations(
            seed_keywords,
            candidate_rows,
            max_keywords=settings.AI_KEYWORD_GAP_RESULT_LIMIT,
        )
    except Exception as exc:
        logger.warning("AI keyword gap filter failed before request: %s", exc)
        ai_recommendations = []

    if ai_recommendations:
        refined = _build_ai_refined_accumulator(accumulator, ai_recommendations, topic_terms)
        if refined:
            logger.info("AI keyword gap filter kept %s of %s candidates", len(refined), len(accumulator))
            return refined

    fallback = _build_heuristic_gap_accumulator(accumulator, candidate_rows)
    logger.info("Heuristic keyword gap filter kept %s of %s candidates", len(fallback), len(accumulator))
    return fallback


def _keyword_gap_candidate_rows(
    db: Session,
    project_id: uuid.UUID,
    accumulator: dict[str, dict[str, Any]],
    topic_terms: set[str] | None,
) -> list[dict[str, Any]]:
    from app.models import Url

    all_url_ids: set[uuid.UUID] = set()
    for data in accumulator.values():
        all_url_ids.update(data.get("url_ids", set()))

    domain_by_url_id: dict[uuid.UUID, str] = {}
    if all_url_ids:
        rows = db.execute(
            select(Url.id, Url.source_domain, Url.url)
            .where(Url.project_id == project_id, Url.id.in_(all_url_ids))
        ).all()
        for url_id, source_domain, url in rows:
            domain = source_domain or _origin(url) or ""
            if domain:
                domain_by_url_id[url_id] = domain

    candidates: list[dict[str, Any]] = []
    for phrase, data in accumulator.items():
        url_ids = data.get("url_ids", set())
        domains = sorted({
            domain_by_url_id[url_id]
            for url_id in url_ids
            if url_id in domain_by_url_id
        })
        score = _gap_candidate_score(phrase, data, domains, topic_terms)
        candidates.append({
            "phrase": phrase,
            "type": data.get("type", "primary"),
            "frequency": int(data.get("count", 1)),
            "competitor_domain_count": len(domains),
            "competitor_domains": domains[:5],
            "score": score,
        })

    candidates.sort(
        key=lambda item: (
            item["score"],
            item["competitor_domain_count"],
            item["frequency"],
            len(item["phrase"].split()),
        ),
        reverse=True,
    )
    return candidates


def _gap_candidate_score(
    phrase: str,
    data: dict[str, Any],
    domains: list[str],
    topic_terms: set[str] | None,
) -> float:
    terms = _phrase_terms(phrase)
    word_count = len(phrase.split())
    frequency = int(data.get("count", 1))
    domain_count = len(domains)
    score = frequency * 2.0 + domain_count * 4.0
    if topic_terms:
        score += len(terms & topic_terms) * 3.0
    if 2 <= word_count <= 5:
        score += 2.0
    if any(term in phrase for term in ("template", "generator", "software", "checker", "calculator", "guide")):
        score += 1.5
    if frequency <= 1 and domain_count <= 1:
        score -= 0.5
    return score


def _build_ai_refined_accumulator(
    accumulator: dict[str, dict[str, Any]],
    ai_recommendations: list[dict[str, Any]],
    topic_terms: set[str] | None,
) -> dict[str, dict[str, Any]]:
    from nlp.keywords import clean_phrase, is_publishable_keyword

    source_lookup = {clean_phrase(phrase): data for phrase, data in accumulator.items()}
    refined: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(ai_recommendations):
        source_phrase = clean_phrase(str(item.get("source_phrase", "")))
        phrase = clean_phrase(str(item.get("phrase", "")))
        keyword_type = str(item.get("type", "lsi")).strip().lower()
        if keyword_type not in {"primary", "lsi", "long-tail"}:
            keyword_type = "lsi"
        if source_phrase not in source_lookup and phrase in source_lookup:
            source_phrase = phrase
        source_data = source_lookup.get(source_phrase)
        if not source_data or not is_publishable_keyword(phrase, min_words=2, topic_terms=topic_terms):
            continue

        if phrase not in refined:
            refined[phrase] = {
                "type": keyword_type,
                "count": 0,
                "url_ids": set(),
                "score": float(len(ai_recommendations) - index),
                "source": "sitemap_ai",
            }
        refined[phrase]["count"] += int(source_data.get("count", 1))
        refined[phrase]["url_ids"].update(source_data.get("url_ids", set()))

    return refined


def _build_heuristic_gap_accumulator(
    accumulator: dict[str, dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    limit = max(1, settings.AI_KEYWORD_GAP_RESULT_LIMIT)
    kept_phrases = {row["phrase"] for row in candidate_rows[:limit]}
    return {
        phrase: data
        for phrase, data in accumulator.items()
        if phrase in kept_phrases
    }


def _store_keywords(db: Session, project_id: uuid.UUID, accumulator: dict[str, dict[str, Any]]) -> None:
    from app.models import Keyword, KeywordUrl

    for phrase, data in accumulator.items():
        if data.get("source") not in {"sitemap", "sitemap_ai"} and data["count"] < 2 and data["type"] in {"primary", "lsi", "heading"}:
            continue
        try:
            keyword = db.execute(
                select(Keyword).where(Keyword.project_id == project_id, Keyword.phrase == phrase)
            ).scalar_one_or_none()
            if not keyword:
                keyword = Keyword(
                    project_id=project_id,
                    phrase=phrase,
                    keyword_type=data["type"],
                    frequency=data["count"],
                )
                db.add(keyword)
                db.flush()
            else:
                keyword.frequency += data["count"]
                keyword.updated_at = datetime.utcnow()

            for url_id in data["url_ids"]:
                exists = db.get(KeywordUrl, (keyword.id, url_id))
                if not exists:
                    db.add(KeywordUrl(keyword_id=keyword.id, url_id=url_id))
            db.commit()
        except Exception as exc:
            logger.warning("Keyword store error for '%s': %s", phrase, exc)
            db.rollback()


def _sync_project_counts(db: Session, project: Any) -> None:
    from app.models import Keyword, Url

    rows = db.execute(
        select(Url.status, func.count(Url.id))
        .where(Url.project_id == project.id)
        .group_by(Url.status)
    ).all()
    status_counts = {status: count for status, count in rows}
    project.urls_found = sum(status_counts.values())
    project.urls_processed = status_counts.get("scraped", 0)
    project.urls_failed = status_counts.get("failed", 0)
    project.total_keywords = db.execute(
        select(func.count(Keyword.id)).where(Keyword.project_id == project.id)
    ).scalar_one()
    db.commit()


try:
    from workers.celery_app import celery_app

    @celery_app.task(name="workers.pipeline.run_full_pipeline")
    def run_full_pipeline_task(project_id: str, scan_job_id: str, resume_existing: bool = False) -> None:
        run_full_pipeline(project_id, scan_job_id, resume_existing)

except ImportError:
    celery_app = None
    run_full_pipeline_task = None
