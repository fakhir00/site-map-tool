"""
Full scan workflow:
discover competitor domains from the main keyword, crawl own and competitor
sitemaps, extract keywords, and persist only competitor keyword gaps.
"""

import gc
import logging
import base64
import re
import threading
import time
import uuid
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from sqlalchemy import create_engine, delete, func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)

sync_engine_kwargs: dict[str, Any] = {
    "pool_pre_ping": True,
}
if "sqlite" in settings.SYNC_DATABASE_URL:
    sync_engine_kwargs["connect_args"] = {"check_same_thread": False, "timeout": 15}
else:
    sync_engine_kwargs["connect_args"] = {
        "connect_timeout": 10,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
    }
    sync_engine_kwargs["pool_size"] = 2
    sync_engine_kwargs["max_overflow"] = 1
    # Hosted Postgres proxies can retire SSL sockets after a short idle period.
    # Prefer the newest pooled connection and recycle before common proxy limits.
    sync_engine_kwargs["pool_recycle"] = 120
    sync_engine_kwargs["pool_use_lifo"] = True

sync_engine = create_engine(settings.SYNC_DATABASE_URL, **sync_engine_kwargs)
SyncSession = sessionmaker(bind=sync_engine, expire_on_commit=False)


def get_db() -> Session:
    return SyncSession()


ACTIVE_SCANS: set[uuid.UUID] = set()
SCAN_EXECUTION_LOCK = threading.Lock()


def is_scan_worker_alive(job_id: uuid.UUID) -> bool:
    return job_id in ACTIVE_SCANS


def trim_memory() -> None:
    """Trigger Python gc and tell glibc to release free arena memory back to the OS."""
    gc.collect()
    try:
        import ctypes
        libc = ctypes.CDLL("libc.so.6")
        libc.malloc_trim(0)
    except Exception:
        pass


def run_full_pipeline(project_id: str, scan_job_id: str, resume_existing: bool = False) -> None:
    """Serialize in-process scans so the web service cannot multiply memory use."""
    logger.info("[%s] Waiting for the scan execution slot", project_id)
    with SCAN_EXECUTION_LOCK:
        _run_full_pipeline(project_id, scan_job_id, resume_existing)


def _run_full_pipeline(project_id: str, scan_job_id: str, resume_existing: bool = False) -> None:
    """
    Run a scan concurrently. URL discovery and scraping run in threads, then
    keyword extraction and AI filtering run once on the full scraped corpus.
    """
    from app.models import Keyword, KeywordUrl, Project, ScanJob, Url
    import concurrent.futures
    import queue
    from datetime import datetime

    project_uuid = uuid.UUID(project_id)
    job_uuid = uuid.UUID(scan_job_id)
    ACTIVE_SCANS.add(job_uuid)
    
    db: Session | None = None
    try:
        from nlp.keywords import classify_keyword_tiers
        from scraping.filters import filter_blog_urls
        from scraping.crawler import scrape_page
        from scraping.sitemap import extract_all_urls_from_domain
        from nlp.openrouter import extract_keywords_from_urls_ai, generate_ai_keywords_sync, ai_generated_source, filter_keyword_gap_recommendations, verify_cluster_intent
        db, project, job = _load_pipeline_state(project_uuid, job_uuid)
        if not project or not job:
            logger.error("[%s] Project or scan job not found", project_id)
            return
        if project.status != "running" or job.status != "queued":
            return

        scan_started = time.monotonic()
        _mark_running(db, project, job)
        logger.info("[%s] Starting concurrent scan for %s", project_id, project.domain)
        audit_summary = project.audit_summary
        stored_seed_keywords = _clean_seed_keywords(project.target_keywords)
        seed_keywords = _scan_seed_keywords(
            stored_seed_keywords,
            project.own_domain or project.domain,
            audit_summary,
        )
        if seed_keywords != stored_seed_keywords:
            project.target_keywords = seed_keywords
            db.commit()
            logger.info(
                "[%s] Repaired scan seeds from EMD/audit context: %s",
                project_id,
                seed_keywords,
            )
        
        # Fix 0: Auto-generate audit context from homepage if missing
        if not audit_summary:
            logger.info("[%s] No audit_summary found — scraping homepage for context", project_id)
            try:
                homepage_url = project.own_domain or project.domain
                if not homepage_url.startswith(("http://", "https://")):
                    homepage_url = f"https://{homepage_url}"
                homepage_result = scrape_page(
                    homepage_url,
                    delay_min=settings.SCRAPE_DELAY_MIN,
                    delay_max=settings.SCRAPE_DELAY_MAX,
                    timeout=settings.REQUEST_TIMEOUT,
                    max_retries=settings.MAX_RETRIES,
                )
                homepage_text = _scrape_result_text(homepage_result)
                if homepage_result and not getattr(homepage_result, "error", None) and len(homepage_text) > 100:
                    import asyncio
                    from nlp.openrouter import generate_gold_hunter_seeds
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    if loop.is_running():
                        # Can't await in running loop — use thread
                        import concurrent.futures as cf
                        with cf.ThreadPoolExecutor(max_workers=1) as ex:
                            fut = ex.submit(asyncio.run, generate_gold_hunter_seeds(homepage_url, homepage_text))
                            gh_result = fut.result(timeout=60)
                    else:
                        gh_result = loop.run_until_complete(generate_gold_hunter_seeds(homepage_url, homepage_text))
                    if gh_result and isinstance(gh_result, dict):
                        audit_summary = gh_result.get("audit_summary", "")
                        if isinstance(audit_summary, dict):
                            import json as _json
                            audit_summary = _json.dumps(audit_summary, indent=2)
                        if audit_summary:
                            project.audit_summary = audit_summary
                            db.commit()
                            logger.info("[%s] Auto-generated audit_summary from homepage", project_id)
            except Exception as e:
                logger.warning("[%s] Failed to auto-generate audit_summary: %s", project_id, e)

        refreshed_seed_keywords = _scan_seed_keywords(
            seed_keywords,
            project.own_domain or project.domain,
            audit_summary,
        )
        if refreshed_seed_keywords != seed_keywords:
            seed_keywords = refreshed_seed_keywords
            project.target_keywords = seed_keywords
            db.commit()
            logger.info("[%s] Added audit-derived scan seed context: %s", project_id, seed_keywords)
        
        semantic_started = time.monotonic()
        topic_terms, negative_terms = _semantic_terms(seed_keywords, audit_summary)
        logger.info("[%s] Semantic filters ready in %.1fs", project_id, time.monotonic() - semantic_started)

        if not _scan_is_active(db, project_uuid, job_uuid):
            return
        db.close()
        db, project, job = _load_pipeline_state(project_uuid, job_uuid)
        if not project or not job or project.status != "running" or job.status != "running":
            return
        if not resume_existing:
            _clear_previous_results(db, project_uuid)
            project.urls_found = 0
            project.urls_processed = 0
            project.urls_failed = 0
            project.total_keywords = 0
            db.commit()

        # Repeat discovery on resume: a pause may have interrupted a domain before
        # its URLs were persisted. Existing scraped pages are retained below.
        db.close()
        db = None
        own_domain = _origin(project.own_domain or project.domain) or project.domain
        competitor_ranking_urls: dict[str, list[str]] = {}
        competitor_diagnostics: list[str] = []
        competitor_domains = _discover_competitor_domains(
            project,
            seed_keywords,
            negative_terms=negative_terms,
            ranking_urls_out=competitor_ranking_urls,
            diagnostics_out=competitor_diagnostics,
        )
        logger.info("[%s] Competitor discovery selected %s domains: %s", project_id, len(competitor_domains), competitor_domains)
        required_terms = _search_required_terms(seed_keywords)
        ranking_terms = _search_ranking_terms(seed_keywords)
        crawl_limit = _crawl_limit_per_domain(competitor_domains)
        if not _scan_is_active(db, project_uuid, job_uuid):
            return
        if db is not None:
            db.close()
        db, project, job = _load_pipeline_state(project_uuid, job_uuid)
        if not project or not job or project.status != "running" or job.status != "running":
            return

        domain_queue = queue.Queue()
        url_queue = queue.Queue()

        existing_sources: set[tuple[str, str]] = set()
        if resume_existing:
            existing_sources = {
                (source_type or "", source_domain or "")
                for source_type, source_domain in db.execute(
                    select(Url.source_type, Url.source_domain).where(Url.project_id == project_uuid)
                ).all()
            }

        if resume_existing:
            existing_pending = db.execute(
                select(Url.id).where(Url.project_id == project_uuid, Url.status == "pending")
            ).scalars().all()
            for u_id in existing_pending:
                url_queue.put(u_id)
            logger.info("[%s] Resumed scan with %s pending URLs pre-queued", project_id, len(existing_pending))

        for domain_item in _domains_to_discover(
            own_domain,
            competitor_domains,
            resume_existing,
            existing_sources,
        ):
            domain_queue.put(domain_item)

        # Discovery and scraping use their own brief sessions. Release this one
        # before network work so no pooled SSL connection sits idle for minutes.
        db.close()
        db = None

        def discover_worker():
            while True:
                try:
                    domain, source_type = domain_queue.get_nowait()
                except queue.Empty:
                    break

                try:
                    patterns = None
                    with get_db() as local_db:
                        if not _scan_is_active(local_db, project_uuid, job_uuid):
                            continue
                        proj = local_db.execute(select(Project).where(Project.id == project_uuid)).scalar_one_or_none()
                        patterns = proj.url_filter_patterns if proj else None

                    d_urls = _discover_content_urls(
                        domain,
                        patterns,
                        extract_all_urls_from_domain,
                        filter_blog_urls,
                        crawl_limit,
                        required_terms,
                        ranking_terms,
                        negative_terms,
                        include_homepage=(source_type == "own"),
                        source_type=source_type,
                        ranking_urls=competitor_ranking_urls.get(domain),
                    )

                    saved_urls = []
                    with get_db() as local_db:
                        if not _scan_is_active(local_db, project_uuid, job_uuid):
                            continue
                        proj = local_db.execute(select(Project).where(Project.id == project_uuid)).scalar_one_or_none()
                        _queue_discovered_urls(
                            local_db,
                            proj,
                            project_uuid,
                            job_uuid,
                            [(url, source_type, domain) for url in d_urls],
                        )

                        saved_urls = local_db.execute(
                            select(Url.id, Url.status).where(Url.project_id == project_uuid, Url.source_domain == domain)
                        ).all()
                        local_db.expunge_all()
                        
                    for u_id, u_status in saved_urls:
                        if u_status == "pending":
                            url_queue.put(u_id)
                except Exception as e:
                    logger.error("Discover worker error for %s: %s", domain, e, exc_info=True)
                finally:
                    domain_queue.task_done()
                
        def scrape_worker():
            try:
                while True:
                    chunk_ids = []
                    try:
                        first_id = url_queue.get(timeout=3.0)
                        chunk_ids.append(first_id)
                    except queue.Empty:
                        if domain_queue.unfinished_tasks == 0 and url_queue.empty():
                            break
                        continue
                        
                    for _ in range(_scrape_chunk_size() - 1):
                        try:
                            chunk_ids.append(url_queue.get_nowait())
                        except queue.Empty:
                            break

                    try:
                        # 1. Quick read: fetch URL strings and verify scan is active, then release DB session
                        chunk_data = []
                        with get_db() as local_db:
                            if not _scan_is_active(local_db, project_uuid, job_uuid):
                                continue
                            chunk_data = local_db.execute(
                                select(Url.id, Url.url).where(Url.id.in_(chunk_ids))
                            ).all()

                        if not chunk_data:
                            continue

                        # 2. Perform web scraping with ZERO open database transaction
                        scraped_results = []
                        for u_id, u_url in chunk_data:
                            if not is_scan_worker_alive(job_uuid):
                                return
                            try:
                                scrape_result = scrape_page(
                                    u_url,
                                    delay_min=settings.SCRAPE_DELAY_MIN,
                                    delay_max=settings.SCRAPE_DELAY_MAX,
                                    timeout=settings.REQUEST_TIMEOUT,
                                    max_retries=settings.MAX_RETRIES,
                                )
                            except Exception as exc:
                                logger.warning("Scrape failed for %s: %s", u_url, exc)
                                scrape_result = None
                            scraped_results.append((u_id, scrape_result))

                        # 3. Quick write: open session, apply results, commit, sync counts, expunge, and close
                        with get_db() as local_db:
                            if not _scan_is_active(local_db, project_uuid, job_uuid):
                                return
                            proj = local_db.execute(select(Project).where(Project.id == project_uuid)).scalar_one_or_none()
                            res_map = {uid: res for uid, res in scraped_results}
                            chunk_rows = local_db.execute(select(Url).where(Url.id.in_(list(res_map.keys())))).scalars().all()
                            for u in chunk_rows:
                                _apply_scrape_result(u, res_map.get(u.id))
                            local_db.commit()
                            if proj:
                                _sync_project_counts(local_db, proj)
                            local_db.expunge_all()

                        trim_memory()

                    except Exception as e:
                        logger.error("Scrape worker chunk error: %s", e, exc_info=True)
                        with get_db() as local_db:
                            _mark_chunk_failed(local_db, project_uuid, chunk_ids, str(e)[:500])
                    finally:
                        for _ in chunk_ids:
                            url_queue.task_done()
            except Exception as e:
                logger.error("Scrape worker error: %s", e, exc_info=True)
        
        scrape_started = time.monotonic()
        n_scrape = max(1, settings.SCRAPE_CONCURRENCY)
        with concurrent.futures.ThreadPoolExecutor(max_workers=n_scrape + 1) as executor:
            discover_futures = [executor.submit(discover_worker) for _ in range(1)]
            scrape_futures = [executor.submit(scrape_worker) for _ in range(n_scrape)]
            
            concurrent.futures.wait(discover_futures)
            concurrent.futures.wait(scrape_futures)

        logger.info("[%s] Discovery and scraping finished in %.1fs", project_id, time.monotonic() - scrape_started)

        if not _scan_is_active(db, project_uuid, job_uuid):
            return

        # The scan can spend several minutes doing network I/O. Never reuse the
        # session opened before that work: its SSL socket may have been retired
        # by the database proxy while it sat idle.
        if db is not None:
            db.close()
        db, project, job = _load_pipeline_state(project_uuid, job_uuid)
        if not project or not job or project.status != "running" or job.status != "running":
            return

        gap_started = time.monotonic()
        competitor_evidence: list[str] = []
        provider_diagnostics: list[str] = []
        dataforseo_count = _process_dataforseo_keywords(
            db,
            project_uuid,
            project.own_domain or project.domain,
            seed_keywords,
            topic_terms,
            negative_terms,
            audit_summary,
            diagnostics=provider_diagnostics,
        )
        logger.info("[%s] DataForSEO pass stored %s keywords", project_id, dataforseo_count)
        competitor_gap_count = _process_competitor_keyword_gaps(
            db,
            project_uuid,
            seed_keywords,
            topic_terms,
            negative_terms,
            audit_summary,
            extract_keywords_from_urls_ai,
            filter_keyword_gap_recommendations,
            classify_keyword_tiers,
            verify_cluster_intent,
            evidence_out=competitor_evidence,
        )
        logger.info(
            "[%s] Competitor keyword gap pass stored %s keywords in %.1fs",
            project_id,
            competitor_gap_count,
            time.monotonic() - gap_started,
        )
            
        if not _scan_is_active(db, project_uuid, job_uuid):
            return
        db.close()
        db, project, job = _load_pipeline_state(project_uuid, job_uuid)
        if not project or not job or project.status != "running" or job.status != "running":
            return
        _ensure_minimum_keyword_count(
            db=db,
            project_id=project_uuid,
            seed_keywords=seed_keywords,
            topic_terms=topic_terms,
            negative_terms=negative_terms,
            audit_summary=audit_summary,
            generate_keywords=generate_ai_keywords_sync,
            ai_generated_source=ai_generated_source,
            evidence_phrases=competitor_evidence,
        )

        if not _scan_is_active(db, project_uuid, job_uuid):
            return
        db.close()
        db, project, job = _load_pipeline_state(project_uuid, job_uuid)
        if not project or not job or project.status != "running" or job.status != "running":
            return
        _sync_project_counts(db, project)
        if not project.total_keywords:
            raise RuntimeError("No keyword gaps could be generated. Check the AI provider configuration and whether competitor pages can be reached, then retry.")

        # ── DeepSeek SEO Enrichment ──────────────────────────────────
        try:
            from nlp.deepseek_seo import enrich_keywords_with_seo_data, is_deepseek_configured
            if is_deepseek_configured():
                unenriched = db.execute(
                    select(Keyword.id, Keyword.phrase).where(
                        Keyword.project_id == project_uuid,
                        Keyword.search_volume.is_(None),
                    )
                ).all()
                if unenriched:
                    phrases = [row[1] for row in unenriched]
                    phrase_to_id = {row[1].strip().lower(): row[0] for row in unenriched}
                    logger.info("[%s] Enriching %s keywords with DeepSeek SEO data", project_id, len(phrases))
                    seo_data = enrich_keywords_with_seo_data(
                        phrases,
                        seed_keywords,
                        audit_summary=audit_summary,
                    )
                    enriched_count = 0
                    for phrase_lower, data in seo_data.items():
                        kw_id = phrase_to_id.get(phrase_lower)
                        if kw_id:
                            db.execute(
                                update(Keyword).where(Keyword.id == kw_id).values(
                                    search_volume=data.get("search_volume"),
                                    difficulty=data.get("difficulty"),
                                    seo_recommendation=data.get("recommendation"),
                                )
                            )
                            enriched_count += 1
                    if enriched_count:
                        db.commit()
                    logger.info("[%s] DeepSeek enriched %s keywords", project_id, enriched_count)
        except Exception as seo_exc:
            logger.warning("[%s] DeepSeek SEO enrichment failed (non-blocking): %s", project_id, seo_exc)
            try:
                db.rollback()
            except Exception:
                pass
        warnings: list[str] = []
        if dataforseo_count == 0:
            warnings.append(
                "DataForSEO: " + provider_diagnostics[0]
                if provider_diagnostics
                else "DataForSEO stored no matching keywords"
            )
        if competitor_gap_count == 0:
            warnings.append(
                (
                    "no direct competitor pages were discovered ("
                    + (
                        competitor_diagnostics[-1]
                        if competitor_diagnostics
                        else "no usable seed or search-provider result was available"
                    )
                    + ")"
                )
                if not competitor_domains
                else "the competitor pages produced no accepted scraped keywords"
            )
        completion_warning = None
        if warnings:
            completion_warning = (
                "Scan completed with limited external research: " + "; ".join(warnings) + ". "
                "Check the provider status cards in Settings and the Render scan logs before retrying."
            )
        _mark_complete(db, project, job, "complete", completion_warning)
        logger.info(
            "[%s] Scan complete with %s keywords in %.1fs",
            project_id,
            project.total_keywords,
            time.monotonic() - scan_started,
        )

    except Exception as exc:
        logger.error("[%s] Pipeline error: %s", project_id, exc, exc_info=True)
        if db is not None:
            try:
                db.rollback()
            except Exception:
                pass
        _record_pipeline_failure(project_uuid, job_uuid, str(exc)[:500])
    finally:
        ACTIVE_SCANS.discard(job_uuid)
        if db is not None:
            db.close()
        try:
            from scraping.crawler import clear_robots_cache
            clear_robots_cache()
        except Exception:
            pass
        trim_memory()

def _discover_content_urls(
    domain: str,
    patterns: list[str] | None,
    extract_all_urls_from_domain: Any,
    filter_blog_urls: Any,
    limit: int,
    required_terms: set[str] | None = None,
    ranking_terms: set[str] | None = None,
    negative_terms: set[str] | None = None,
    include_homepage: bool = False,
    source_type: str = "competitor",
    ranking_urls: list[str] | None = None,
) -> list[str]:
    max_raw_urls = min(1000, max(limit * 10, limit + 25))
    
    all_urls = extract_all_urls_from_domain(
        domain,
        timeout=settings.REQUEST_TIMEOUT,
        max_urls=max_raw_urls,
    )
    verified_ranking_urls = list(dict.fromkeys(ranking_urls or []))
    all_urls = list(dict.fromkeys([*verified_ranking_urls, *all_urls]))
    if source_type == "competitor" and len(all_urls) <= 1:
        try:
            from scraping.apify_client_module import crawl_competitor_content_via_apify, is_apify_configured
            if is_apify_configured():
                apify_urls = crawl_competitor_content_via_apify(domain, max_pages=min(limit, 20))
                all_urls = list(dict.fromkeys([*all_urls, *apify_urls]))
                logger.info("Apify crawl expanded %s to %s discovered URLs", domain, len(all_urls))
        except Exception as exc:
            logger.warning("Apify competitor crawl fallback failed for %s: %s", domain, exc)
        
    logger.info("Found %s sitemap URLs for %s", len(all_urls), domain)
    if source_type == "own":
        # For the user's own domain, we want to analyze ALL content to find gaps, 
        # not just blogs. Our negative_terms filter will still remove junk.
        content_urls = list(all_urls)
    else:
        content_urls = filter_blog_urls(
            all_urls,
            patterns=patterns,
            domain=domain,
        )
        # These exact pages ranked in Google for a supplied seed. Keep them even
        # when a site's URL structure does not resemble /blog/ or /article/.
        content_urls = list(dict.fromkeys([*verified_ranking_urls, *content_urls]))
    content_urls = [url for url in content_urls if _is_relevant_content_url(url, required_terms or set(), negative_terms)]
    if required_terms:
        topical_urls = [url for url in content_urls if _url_has_any_terms(url, required_terms)]
        if len(topical_urls) >= limit:
            content_urls = list(dict.fromkeys([*verified_ranking_urls, *topical_urls]))
    verified_ranking_set = set(verified_ranking_urls)
    content_urls.sort(
        key=lambda url: (
            url in verified_ranking_set,
            _url_relevance_score(url, ranking_terms or set()),
        ),
        reverse=True,
    )
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


def _crawl_limit_per_domain(competitor_domains: list[str]) -> int:
    domain_count = max(1, len(competitor_domains) + 1)
    configured_per_domain = max(1, int(settings.MAX_CONTENT_URLS_PER_DOMAIN))
    global_per_domain = max(1, int(settings.MAX_URLS_PER_SCAN) // domain_count)
    return max(1, min(12, configured_per_domain, global_per_domain))


def _domains_to_discover(
    own_domain: str,
    competitor_domains: list[str],
    resume_existing: bool,
    existing_sources: set[tuple[str, str]],
) -> list[tuple[str, str]]:
    """On resume, enqueue each source that has not persisted any URL yet."""
    queued: list[tuple[str, str]] = []
    if not resume_existing or not any(source_type == "own" for source_type, _ in existing_sources):
        queued.append((own_domain, "own"))
    for domain in competitor_domains:
        if not resume_existing or ("competitor", domain) not in existing_sources:
            queued.append((domain, "competitor"))
    return queued


def _scrape_chunk_size() -> int:
    # Persist each small batch before fetching more pages. This bounds live DOM,
    # response, extracted-text, and ORM objects in the shared Render web process.
    return max(1, min(2, int(settings.MAX_CONTENT_URLS_PER_DOMAIN)))


def _mark_chunk_failed(
    db: Session,
    project_id: uuid.UUID,
    chunk_ids: list[uuid.UUID],
    reason: str,
) -> None:
    if not chunk_ids:
        return

    from app.models import Project, Url

    try:
        rows = db.execute(select(Url).where(Url.id.in_(chunk_ids))).scalars().all()
        for url_record in rows:
            if url_record.status == "pending":
                url_record.status = "failed"
                url_record.error_reason = f"Worker error: {reason}"[:500]
                url_record.scraped_at = datetime.utcnow()
        db.commit()

        project = db.execute(select(Project).where(Project.id == project_id)).scalar_one_or_none()
        if project:
            _sync_project_counts(db, project)
    except Exception:
        db.rollback()


def _process_competitor_keyword_gaps(
    db: Session,
    project_id: uuid.UUID,
    seed_keywords: list[str],
    topic_terms: set[str] | None,
    negative_terms: set[str] | None,
    audit_summary: str | None,
    extract_keywords_from_urls_ai: Any,
    filter_keyword_gap_recommendations: Any,
    classify_keyword_tiers: Any,
    verify_cluster_intent: Any,
    evidence_out: list[str] | None = None,
) -> int:
    from app.models import Url

    base_query = (
        select(Url)
        .where(
            Url.project_id == project_id,
            Url.source_type == "competitor",
            Url.status == "scraped",
        )
    )
    count = db.execute(select(func.count()).select_from(base_query.subquery())).scalar()
    if not count:
        return 0

    logger.info("Extracting keyword candidates from %s scraped competitor URLs", count)
    
    url_stream = db.execute(
        base_query.order_by(Url.source_domain.asc(), Url.url.asc())
    ).yield_per(10).scalars()

    extracted = extract_keywords_from_urls_ai(
        seed_keywords,
        url_stream,
        topic_terms=topic_terms,
        negative_terms=negative_terms,
    )
    extracted = [
        item for item in extracted
        if _keyword_matches_topic(str(item.get("phrase") or ""), seed_keywords, topic_terms, negative_terms)
    ]
    if evidence_out is not None:
        evidence_out.extend(
            str(item.get("phrase") or "") for item in extracted if item.get("phrase")
        )
    if not extracted:
        return 0

    filtered = filter_keyword_gap_recommendations(
        seed_keywords,
        extracted,
        audit_summary=audit_summary,
        max_keywords=settings.AI_KEYWORD_GAP_RESULT_LIMIT,
    )
    # The candidates already passed deterministic topical and quality checks.
    # An empty/invalid model response must not erase all observed evidence.
    if not filtered:
        if filtered == []:
            logger.warning(
                "AI gap filter returned no selections; retaining mechanically verified competitor phrases"
            )
        filtered = _fallback_gap_recommendations(
            extracted,
            settings.AI_KEYWORD_GAP_RESULT_LIMIT,
        )
    from nlp.keywords import is_publishable_keyword
    filtered = [
        item for item in filtered
        if is_publishable_keyword(
            str(item.get("phrase") or ""),
            min_words=2,
            negative_terms=negative_terms,
        )
        and _keyword_matches_topic(
            str(item.get("phrase") or ""),
            seed_keywords,
            topic_terms,
            negative_terms,
        )
    ]
    filtered = _with_source_url_ids(filtered, extracted)
    logger.info(
        "Competitor keyword filter retained %s of %s extracted phrases",
        len(filtered),
        len(extracted),
    )
    if not filtered:
        return 0

    acc: dict[str, dict[str, Any]] = {}
    # Keep every evidence-backed keyword here. Page-level consolidation belongs
    # to the hub builder; merging at ingestion was collapsing 100 useful
    # keyword variations into fewer than ten database rows.
    for item in filtered:
        phrase = str(item.get("phrase") or "").strip().lower()
        if not phrase:
            continue
        url_ids = _coerce_uuid_set(item.get("url_ids", []))
        if phrase not in acc:
            acc[phrase] = {
                "type": item.get("type", "lsi"),
                "count": 0,
                "url_ids": set(),
                "score": 1.0,
                "source": "sitemap",
                "tier": "outlier",
            }
        acc[phrase]["count"] += max(1, int(item.get("frequency") or len(url_ids) or 1))
        acc[phrase]["url_ids"].update(url_ids)

    own_phrases = _own_content_keyword_phrases(db, project_id, topic_terms, negative_terms)
    _remove_covered_keywords(acc, own_phrases)
    if not acc:
        return 0

    _store_keywords(db, project_id, acc)
    return len(acc)


def _process_dataforseo_keywords(
    db: Session,
    project_id: uuid.UUID,
    domain: str,
    seed_keywords: list[str],
    topic_terms: set[str] | None,
    negative_terms: set[str] | None,
    audit_summary: str | None = None,
    diagnostics: list[str] | None = None,
) -> int:
    """Store paid-provider keywords only after deterministic relevance checks."""
    from app.models import Url
    from nlp.dataforseo import collect_keyword_research, is_dataforseo_configured
    from nlp.keywords import clean_phrase, is_publishable_keyword

    if not is_dataforseo_configured():
        logger.error("DataForSEO skipped: no complete credential pair is configured")
        if diagnostics is not None:
            diagnostics.append("no complete credential pair is configured")
        return 0
    research = collect_keyword_research(
        db,
        _registered_domain(domain) or domain,
        seed_keywords,
        audit_summary,
    )
    logger.info(
        "DataForSEO exact-seed research returned %s candidates for seeds %s",
        len(research.keywords),
        seed_keywords,
    )
    if diagnostics is not None:
        diagnostics.extend(research.errors)
    accepted = []
    for item in research.keywords:
        phrase = clean_phrase(str(item.get("phrase") or ""))
        if not is_publishable_keyword(phrase, min_words=2, negative_terms=negative_terms):
            continue
        if not _keyword_matches_topic(phrase, seed_keywords, topic_terms, negative_terms):
            continue
        accepted.append({**item, "phrase": phrase})
    if not accepted:
        logger.warning(
            "DataForSEO returned %s candidates but none passed the site relevance boundary",
            len(research.keywords),
        )
        if diagnostics is not None and not research.errors:
            diagnostics.append(
                f"exact-seed suggestions returned {len(research.keywords)} candidates "
                f"for {len(seed_keywords)} seeds but none passed the site relevance boundary"
            )
        return 0

    source_url = "https://dataforseo.com/"
    source = db.execute(
        select(Url).where(Url.project_id == project_id, Url.url == source_url)
    ).scalar_one_or_none()
    if not source:
        source = Url(
            project_id=project_id,
            url=source_url,
            source_type="provider",
            source_domain="DataForSEO",
            status="scraped",
        )
        db.add(source)
        db.flush()

    accumulator: dict[str, dict[str, Any]] = {}
    for item in accepted:
        accumulator[item["phrase"]] = {
            "type": item.get("type") or "long-tail",
            "count": 1,
            "url_ids": {source.id},
            "score": float(item.get("search_volume") or 1),
            "source": "sitemap_ai",
            "tier": "outlier",
            "search_volume": item.get("search_volume"),
            "difficulty": item.get("difficulty"),
        }
    _store_keywords(db, project_id, accumulator)
    logger.info(
        "DataForSEO accepted %s of %s exact-seed candidates",
        len(accumulator),
        len(research.keywords),
    )
    return len(accumulator)


def _fallback_gap_recommendations(candidates: list[dict[str, Any]], max_keywords: int) -> list[dict[str, Any]]:
    from nlp.keywords import STOPWORDS, clean_phrase

    ranked = sorted(candidates, key=_gap_recommendation_rank, reverse=True)
    kept: list[dict[str, Any]] = []
    seen_signatures: set[tuple[str, ...]] = set()

    for item in ranked:
        phrase = clean_phrase(str(item.get("phrase") or ""))
        if not phrase:
            continue
        signature = tuple(sorted(word for word in phrase.split() if word not in STOPWORDS))
        if not signature or signature in seen_signatures:
            continue
        kept.append({
            **item,
            "source_phrase": item.get("source_phrase") or phrase,
            "phrase": phrase,
            "volume": item.get("volume") or "Medium",
        })
        seen_signatures.add(signature)
        if len(kept) >= max_keywords:
            break

    return kept


def _gap_recommendation_rank(item: dict[str, Any]) -> tuple[int, int, int, int]:
    phrase = str(item.get("phrase") or "")
    word_count = len(phrase.split())
    url_count = len(item.get("url_ids") or [])
    frequency = int(item.get("frequency") or url_count or 1)
    ideal_length_bonus = 1 if 2 <= word_count <= 5 else 0
    return url_count, frequency, ideal_length_bonus, -abs(4 - word_count)


def _with_source_url_ids(
    recommendations: list[dict[str, Any]],
    source_candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    from nlp.keywords import clean_phrase

    source_lookup: dict[str, dict[str, Any]] = {}
    for source in source_candidates:
        for key in (
            clean_phrase(str(source.get("source_phrase") or "")),
            clean_phrase(str(source.get("phrase") or "")),
        ):
            if key and key not in source_lookup:
                source_lookup[key] = source

    enriched: list[dict[str, Any]] = []
    for item in recommendations or []:
        phrase = clean_phrase(str(item.get("phrase") or ""))
        source_phrase = clean_phrase(str(item.get("source_phrase") or ""))
        source = source_lookup.get(source_phrase) or source_lookup.get(phrase)
        enriched_item = dict(item)
        if source:
            enriched_item.setdefault("source_phrase", source.get("phrase") or source.get("source_phrase"))
            if not enriched_item.get("url_ids"):
                enriched_item["url_ids"] = list(source.get("url_ids") or [])
            if not enriched_item.get("frequency"):
                enriched_item["frequency"] = source.get("frequency") or len(source.get("url_ids") or []) or 1
        if phrase:
            enriched_item["phrase"] = phrase
            enriched.append(enriched_item)

    return enriched


def _coerce_uuid_set(values: Any) -> set[uuid.UUID]:
    result: set[uuid.UUID] = set()
    for value in values or []:
        if isinstance(value, uuid.UUID):
            result.add(value)
            continue
        try:
            result.add(uuid.UUID(str(value)))
        except (TypeError, ValueError, AttributeError):
            pass
    return result


def _scrape_result_text(scrape_result: Any) -> str:
    if not scrape_result:
        return ""

    text = getattr(scrape_result, "text_content", None)
    if text is None:
        text = getattr(scrape_result, "text", "")
    return text if isinstance(text, str) else str(text or "")


def _scrape_error_reason(scrape_result: Any, text: str) -> str | None:
    if not scrape_result:
        return "No scrape response"

    error = getattr(scrape_result, "error", None)
    if error:
        return str(error)

    if not text.strip():
        return "No readable text extracted"

    return None


def _apply_scrape_result(url_record: Any, scrape_result: Any) -> bool:
    text = _scrape_result_text(scrape_result)
    # Truncate to save memory — 15k chars is plenty for keyword extraction
    if text and len(text) > settings.MAX_SCRAPED_TEXT_LENGTH:
        text = text[:settings.MAX_SCRAPED_TEXT_LENGTH]
    url_record.scraped_text = text
    url_record.h1 = (
        getattr(scrape_result, "h1", None)
        if scrape_result
        else None
    ) or _url_display_title(url_record.url)
    url_record.word_count = (
        getattr(scrape_result, "word_count", 0)
        if scrape_result
        else 0
    ) or (len(text.split()) if text else 0)
    url_record.readability_score = (
        getattr(scrape_result, "readability_score", 0.0)
        if scrape_result
        else 0.0
    ) or 0.0
    url_record.publish_date = (
        getattr(scrape_result, "publish_date", None)
        if scrape_result
        else None
    )
    url_record.scraped_at = datetime.utcnow()

    error_reason = _scrape_error_reason(scrape_result, text)
    if error_reason:
        url_record.status = "failed"
        url_record.error_reason = error_reason[:500]
        return False

    url_record.status = "scraped"
    url_record.error_reason = None
    return True


def _discover_competitor_domains(
    project: Any,
    seed_keywords: list[str],
    negative_terms: set[str] | None = None,
    ranking_urls_out: dict[str, list[str]] | None = None,
    diagnostics_out: list[str] | None = None,
) -> list[str]:
    if ranking_urls_out is not None:
        ranking_urls_out.clear()
    if not seed_keywords:
        logger.warning("No primary keyword provided, competitor discovery skipped")
        return []

    own_root = _registered_domain(project.own_domain or project.domain)
    required_terms = _search_required_terms(seed_keywords)
    # Allow up to eighteen direct competitors across 3-5 exact seeds while the
    # global URL ceiling continues to bound scraping memory.
    # The old max(20, setting) silently defeated lower-memory configuration and
    # could schedule more than 500 full-page scrapes in the API process.
    competitor_limit = max(3, min(25, int(settings.MAX_COMPETITOR_DOMAINS)))
    candidate_limit = max(competitor_limit * 3, settings.MAX_COMPETITOR_JUDGE_CANDIDATES)
    # Reserve discovery capacity for every Gold Hunter seed. A global limit here
    # previously let the first seed exhaust the pool before later seeds ran.
    serp_limit = max(20, settings.GOOGLE_SERP_RESULT_LIMIT)
    per_kw_limit = max(4, min(serp_limit, candidate_limit // len(seed_keywords)))
    search_locale = getattr(project, 'search_locale', 'us') or 'us'
    competitor_domains: list[str] = []
    competitor_roots: set[str] = set()
    candidate_signals: dict[str, dict[str, Any]] = {}
    apify_result_count = 0
    fallback_result_count = 0
    
    from scraping.apify_client_module import search_google_via_apify, is_apify_configured

    def selected(domains: list[str]) -> list[str]:
        if ranking_urls_out is not None:
            for domain in domains:
                sample_urls = (candidate_signals.get(domain) or {}).get("sample_urls") or []
                ranking_urls_out[domain] = list(dict.fromkeys(sample_urls))[:3]
        return domains

    def add_domain(
        url: str | None,
        query: str,
        source: str,
        rank: int,
        title: str | None = None,
        snippet: str | None = None,
    ) -> None:
        unwrapped_url = _unwrap_result_url(url)
        if not _is_relevant_result_url(unwrapped_url, required_terms, negative_terms):
            return
        domain = _origin(unwrapped_url)
        root = _registered_domain(domain)
        if not domain or not root:
            return
        if root == own_root or _is_blocked_competitor_root(root):
            return
        signal = candidate_signals.setdefault(domain, {
            "domain": domain,
            "sample_urls": [],
            "queries": [],
            "sources": [],
            "best_rank": rank,
            "titles": [],
            "snippets": [],
        })
        if unwrapped_url and unwrapped_url not in signal["sample_urls"]:
            signal["sample_urls"].append(unwrapped_url)
        if query not in signal["queries"]:
            signal["queries"].append(query)
        if source not in signal["sources"]:
            signal["sources"].append(source)
        signal["best_rank"] = min(int(signal.get("best_rank") or rank), rank)
        if title and title not in signal["titles"]:
            signal["titles"].append(title[:250])
        if snippet and snippet not in signal["snippets"]:
            signal["snippets"].append(snippet[:500])
        if root not in competitor_roots:
            competitor_domains.append(domain)
            competitor_roots.add(root)

    for kw in seed_keywords:
        kw = kw.strip()
        if not kw: continue
        
        logger.info(f"Discovering competitors for keyword: {kw}")
        start_count = len(competitor_domains)
        
        # 1. Primary explicit search for this specific keyword
        primary_results_added = False
        if is_apify_configured():
            apify_results = search_google_via_apify(kw, max_results=serp_limit, country_code=search_locale)
            apify_result_count += len(apify_results)
            logger.info("Apify returned %s organic results for exact seed %r", len(apify_results), kw)
            for rank, res in enumerate(apify_results, start=1):
                before = len(competitor_domains)
                add_domain(
                    res.get("url"), kw, "apify_page_1", rank,
                    res.get("title"), res.get("snippet"),
                )
                primary_results_added = primary_results_added or len(competitor_domains) > before
                if len(competitor_domains) - start_count >= per_kw_limit:
                    break

        if not primary_results_added and len(competitor_domains) - start_count < per_kw_limit:
            remaining = per_kw_limit - (len(competitor_domains) - start_count)
            for rank, href in enumerate(
                _search_result_urls(kw, include_google=True, locale=search_locale, max_results=remaining),
                start=1,
            ):
                fallback_result_count += 1
                add_domain(href, kw, "google_page_1", rank)
                if len(competitor_domains) - start_count >= per_kw_limit:
                    break

    # Hosted search engines commonly challenge datacenter IPs. Use a cached,
    # exact-seed DataForSEO SERP only when every existing discovery route found
    # nothing. Usually the first seed supplies enough domains, limiting spend to
    # a single small SERP request rather than charging on every scan path.
    if not competitor_domains:
        try:
            from nlp.dataforseo import search_competitors
            for kw in seed_keywords:
                with get_db() as provider_db:
                    provider_results = search_competitors(
                        provider_db, kw, locale=search_locale, max_results=serp_limit,
                    )
                for rank, res in enumerate(provider_results, start=1):
                    add_domain(
                        res.get("url"), kw, "dataforseo_serp", rank,
                        res.get("title"), res.get("snippet"),
                    )
                if len(competitor_domains) >= max(3, min(competitor_limit, per_kw_limit)):
                    break
        except Exception as exc:
            logger.warning("DataForSEO competitor discovery fallback failed: %s", exc)

    balanced_domains = _balanced_competitor_domains(
        competitor_domains, candidate_signals, seed_keywords, candidate_limit,
    )
    llm_domains = _llm_filter_competitor_domains(
        seed_keywords,
        project.own_domain or project.domain,
        [candidate_signals[domain] for domain in balanced_domains if domain in candidate_signals],
        competitor_limit,
        project.audit_summary,
    )
    evidence_fallback = _high_confidence_competitor_fallback(
        balanced_domains,
        candidate_signals,
        seed_keywords,
        competitor_limit,
    )
    if llm_domains is not None:
        if llm_domains:
            combined = list(llm_domains)
            for domain in evidence_fallback:
                if domain not in combined:
                    combined.append(domain)
            result = selected(combined[:competitor_limit])
            if diagnostics_out is not None:
                diagnostics_out.append(
                    f"Apify returned {apify_result_count} organic results; "
                    f"{len(balanced_domains)} candidate sites; {len(result)} direct competitors selected"
                )
            return result
        if evidence_fallback:
            logger.warning(
                "Competitor judge rejected every candidate; retained %s registered-domain EMD matches",
                len(evidence_fallback),
            )
            result = selected(evidence_fallback)
            if diagnostics_out is not None:
                diagnostics_out.append(
                    f"Apify returned {apify_result_count} organic results; "
                    f"the AI judge selected none; {len(result)} EMD-matched competitors rescued"
                )
            return result
        if diagnostics_out is not None:
            diagnostics_out.append(
                f"Apify returned {apify_result_count} organic results; "
                f"{len(balanced_domains)} candidate sites; none matched the direct-site boundary"
            )
        return []

    result = selected(balanced_domains[:competitor_limit])
    if diagnostics_out is not None:
        diagnostics_out.append(
            f"Apify returned {apify_result_count} organic results; "
            f"fallback search returned {fallback_result_count}; {len(result)} competitors selected"
        )
    return result


def _high_confidence_competitor_fallback(
    domains: list[str],
    signals: dict[str, dict[str, Any]],
    seed_keywords: list[str],
    limit: int,
) -> list[str]:
    """Rescue only focused domains whose registered name matches an exact seed."""
    accepted: list[str] = []
    for domain in domains:
        signal = signals.get(domain) or {}
        queries = signal.get("queries") or []
        for seed in seed_keywords:
            if seed not in queries:
                continue
            if _domain_matches_seed_scope(domain, seed):
                accepted.append(domain)
                break
        if len(accepted) >= limit:
            break
    return accepted


def _balanced_competitor_domains(
    domains: list[str],
    signals: dict[str, dict[str, Any]],
    seed_keywords: list[str],
    limit: int,
) -> list[str]:
    """Round-robin candidates so each seed is represented before filling extras."""
    buckets = [
        [domain for domain in domains if seed in signals.get(domain, {}).get("queries", [])]
        for seed in seed_keywords
    ]
    result: list[str] = []
    index = 0
    while len(result) < limit and any(index < len(bucket) for bucket in buckets):
        for bucket in buckets:
            if index < len(bucket) and bucket[index] not in result:
                result.append(bucket[index])
                if len(result) >= limit:
                    return result
        index += 1
    for domain in domains:
        if domain not in result:
            result.append(domain)
            if len(result) >= limit:
                break
    return result


def _primary_competitor_search_query(seed_keywords: list[str]) -> str:
    phrase = " ".join(seed_keywords[:4]).strip()
    return f'"{phrase}"'


def _fallback_competitor_domains(seed_keywords: list[str]) -> list[str]:
    # We no longer use hardcoded fallback domains as it violates niche-agnosticism.
    # Rely entirely on the Google/Bing/DDG/Apify scrapers.
    return []


def _search_result_urls(
    query: str,
    include_google: bool = False,
    locale: str = "us",
    max_results: int | None = None,
) -> list[str]:
    urls: list[str] = []

    def add_results(results: list[str]) -> bool:
        for url in results:
            normalized = _unwrap_result_url(url)
            root = _registered_domain(normalized)
            if not normalized or not root or _is_blocked_search_result_root(root):
                continue
            if normalized not in urls:
                urls.append(normalized)
            if max_results is not None and len(urls) >= max_results:
                return True
        return False

    if include_google:
        if add_results(_search_google_result_urls(query, max_results=settings.GOOGLE_SERP_RESULT_LIMIT, locale=locale)):
            return urls
    if add_results(_search_bing_result_urls(query)):
        return urls
    add_results(_search_duckduckgo_html_urls(query))
    return list(dict.fromkeys(urls))


def _competitor_search_queries(seed_keywords: list[str]) -> list[str]:
    queries: list[str] = []
    modifiers = ["alternative", "competitor", "review", "comparison", "online"]

    for keyword in seed_keywords:
        queries.append(keyword)
        base_terms = set(keyword.lower().split())

        for mod in modifiers:
            if mod not in base_terms:
                queries.append(f'{keyword} {mod}')

        if len(base_terms) >= 2:
            longest_word = max(base_terms, key=len)
            for mod in modifiers:
                if mod not in base_terms:
                    queries.append(f'{longest_word} {mod}')

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


def _url_has_any_terms(url: str, terms: set[str]) -> bool:
    lowered = unquote(urlparse(url).path).lower()
    path_words = set(re.findall(r"[a-z0-9]{2,}", lowered))
    return bool(path_words & terms)


def _is_relevant_result_url(url: str | None, required_terms: set[str], negative_terms: set[str] | None = None) -> bool:
    """Filter competitor discovery URLs. Trust Google rankings but block obviously irrelevant URLs."""
    if not url:
        return False
    lowered = unquote(urlparse(url).path).lower()
    # Block URLs whose path contains negative terms from the audit
    if negative_terms:
        path_words = set(re.findall(r'[a-z]{3,}', lowered))
        if path_words & negative_terms:
            return False
    # Trust Google's ranking — if it returned this result for our seed query, accept it
    return True


def _is_relevant_content_url(url: str, required_terms: set[str], negative_terms: set[str] | None = None) -> bool:
    """Filter sitemap URLs. Accept content pages, reject junk and negatively-tagged URLs."""
    if not url:
        return False
    lowered = urlparse(url).path.lower()
    
    # Filter out binary/junk extensions
    if lowered.endswith((".pdf", ".jpg", ".png", ".gif", ".zip", ".exe", ".mp3", ".mp4", ".svg")):
        return False
    
    # Block URLs whose path contains negative terms from the audit
    if negative_terms:
        path_words = set(re.findall(r'[a-z]{3,}', lowered))
        if path_words & negative_terms:
            return False
        
    return True


def _search_google_result_urls(query: str, max_results: int = 10, locale: str = "us") -> list[str]:
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
                "gl": locale,
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
    from nlp.keywords import normalize_seed_keywords

    cleaned_keywords: list[str] = []
    for cleaned in normalize_seed_keywords(raw_keywords):
        for candidate in _expand_seed_keyword(cleaned):
            if candidate not in cleaned_keywords:
                cleaned_keywords.append(candidate)
    return cleaned_keywords


def _scan_seed_keywords(
    stored_keywords: list[str],
    domain: str | None,
    audit_summary: str | None,
) -> list[str]:
    """Build a bounded, EMD-first seed set and repair stale legacy projects."""
    import json
    from nlp.keywords import clean_phrase

    seeds = list(dict.fromkeys(_clean_seed_keywords(stored_keywords)))
    audit_primary = ""
    try:
        audit = json.loads(audit_summary) if audit_summary else {}
        if isinstance(audit, dict):
            audit_primary = clean_phrase(str(audit.get("primary_keyword") or ""))
    except (TypeError, json.JSONDecodeError):
        pass

    if audit_primary and audit_primary not in seeds:
        if not seeds or _domain_matches_seed_scope(domain or "", audit_primary):
            seeds.append(audit_primary)

    ordered = _order_seeds_by_emd(seeds, domain)
    if any(_domain_matches_seed_scope(domain or "", seed) for seed in ordered):
        return ordered[:5]

    # A legacy project can contain a stale AI seed unrelated to its EMD. A
    # descriptive TLD supplies a safe recovery query without trying to invent
    # word boundaries inside arbitrary brand names.
    registered = _registered_domain(domain)
    if registered:
        host = urlparse(f"https://{registered}").hostname or ""
        parts = host.lower().removeprefix("www.").split(".")
        label = parts[0] if parts else ""
        suffix = parts[-1] if len(parts) > 1 else ""
        if label and suffix in {"review", "reviews", "tools"}:
            label = re.sub(r"([a-z])([0-9])", r"\1 \2", label)
            recovery_seed = clean_phrase(f"{label} {suffix}")
            if recovery_seed and recovery_seed not in ordered:
                ordered.insert(0, recovery_seed)

    return _order_seeds_by_emd(ordered, domain)[:5]


def _expand_seed_keyword(keyword: str) -> list[str]:
    # We no longer split compound keywords using hardcoded dictionary lookups
    # (e.g. splitting "circuitdiagrammaker" to "circuit diagram maker")
    # since it violates niche-agnosticism.
    return [keyword]


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

        # Use tldextract's bundled public-suffix snapshot. Runtime downloads and
        # cache locks are unnecessary in a short-lived hosted worker and used to
        # make subdomains look like registered roots when the cache was unwritable.
        extractor = getattr(_registered_domain, "_extractor", None)
        if extractor is None:
            extractor = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)
            setattr(_registered_domain, "_extractor", extractor)
        extracted = extractor(host)
        if extracted.domain and extracted.suffix:
            return f"{extracted.domain}.{extracted.suffix}"
    except Exception:
        pass
    return host


def _domain_matches_seed_scope(domain: str, seed: str) -> bool:
    """Return true only when the registered domain itself carries the seed entity."""
    from nlp.keywords import BROAD_TOPIC_TERMS, GENERIC_TOOL_TERMS, clean_phrase

    root = _registered_domain(domain)
    if not root or _is_blocked_competitor_root(root):
        return False
    label = root.lower().split(".")[0]
    compact_label = re.sub(r"[^a-z0-9]", "", label)
    words = clean_phrase(seed).split()
    intent_terms = {
        "best", "buy", "comparison", "cost", "free", "guide", "online",
        "price", "pricing", "rating", "ratings", "review", "reviews",
        "vs", "website",
    }
    entity_words = [
        word for word in words
        if word not in BROAD_TOPIC_TERMS
        and word not in GENERIC_TOOL_TERMS
        and word not in intent_terms
    ]
    entity = re.sub(r"[^a-z0-9]", "", "".join(entity_words))
    compact_seed = re.sub(r"[^a-z0-9]", "", "".join(words))
    if len(entity) >= 5 and entity in compact_label:
        return True
    return len(compact_seed) >= 7 and (
        compact_seed in compact_label
        or (len(compact_label) >= 7 and compact_label in compact_seed)
    )


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
        "quora.com",
        "reddit.com",
        "tenereteam.com",
        "tiktok.com",
        "trustpilot.com",
        "wikipedia.org",
        "x.com",
        "yahoo.com",
        "yellowpages.com",
        "youtube.com",
    }
    if root in blocked_roots:
        return True
    label = root.lower().split(".")[0]
    blocked_label_terms = {
        "coupon", "coupons", "deal", "deals", "directory", "forum",
        "forums", "marketplace", "social", "wiki",
    }
    return bool(set(re.findall(r"[a-z]+", label)) & blocked_label_terms)


def _mark_running(db: Session, project: Any, job: Any) -> None:
    now = datetime.utcnow()
    project.status = "running"
    job.status = "running"
    job.started_at = job.started_at or now
    job.error_message = None
    db.commit()


def _retry_database_connection(attempt: int, operation: str, exc: Exception) -> None:
    """Discard broken pooled sockets and briefly wait for hosted Postgres to recover."""
    try:
        sync_engine.dispose()
    except Exception:
        pass
    delay = min(0.25 * (2 ** attempt), 2.0)
    logger.warning("Database connection failed during %s; retrying in %.2fs: %s", operation, delay, exc)
    time.sleep(delay)


def _load_pipeline_state(
    project_id: uuid.UUID,
    job_id: uuid.UUID,
    attempts: int = 6,
) -> tuple[Session, Any, Any]:
    """Open a usable session and load the scan's current records."""
    from app.models import Project, ScanJob
    from sqlalchemy.exc import DBAPIError

    last_error: Exception | None = None
    for attempt in range(attempts):
        db = get_db()
        try:
            project = db.execute(select(Project).where(Project.id == project_id)).scalar_one_or_none()
            job = db.execute(select(ScanJob).where(ScanJob.id == job_id)).scalar_one_or_none()
            return db, project, job
        except DBAPIError as exc:
            last_error = exc
            try:
                db.rollback()
            except Exception:
                pass
            db.close()
            if attempt + 1 < attempts:
                _retry_database_connection(attempt, "loading scan state", exc)
    assert last_error is not None
    raise last_error


def _scan_is_active(_db: Session | None, project_id: uuid.UUID, job_id: uuid.UUID) -> bool:
    """Read state on a fresh connection so an idle SSL socket cannot kill a scan."""
    from app.models import Project, ScanJob
    from sqlalchemy.exc import DBAPIError

    row = None
    last_error: Exception | None = None
    for attempt in range(5):
        status_db = get_db()
        try:
            with status_db.no_autoflush:
                row = status_db.execute(select(Project.status, ScanJob.status, ScanJob.started_at)
                    .join(ScanJob, ScanJob.project_id == Project.id)
                    .where(Project.id == project_id, ScanJob.id == job_id)).first()
            break
        except DBAPIError as exc:
            last_error = exc
            try:
                status_db.rollback()
            except Exception:
                pass
            if attempt < 4:
                _retry_database_connection(attempt, "scan status check", exc)
        finally:
            status_db.close()
    if row is None and last_error is not None:
        # A temporary database outage must not turn a healthy scraping worker
        # into an errored scan. The next checkpoint will verify state again.
        if job_id in ACTIVE_SCANS:
            logger.error("Scan status could not be read after retries; keeping active worker alive: %s", last_error)
            return True
        return False
    if not row or row[0] != "running" or row[1] != "running":
        return False
    if row[2] and (datetime.utcnow() - row[2].replace(tzinfo=None)).total_seconds() > settings.SCAN_MAX_SECONDS:
        raise TimeoutError("Scan exceeded its time limit. Please retry.")
    return True


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
    db.commit()


def _record_pipeline_failure(project_id: uuid.UUID, job_id: uuid.UUID, error_msg: str) -> None:
    """Persist a terminal error using reconnects, without masking the original failure."""
    from sqlalchemy.exc import DBAPIError

    for attempt in range(6):
        db: Session | None = None
        try:
            db, project, job = _load_pipeline_state(project_id, job_id, attempts=1)
            if job and job.status in {"queued", "running"}:
                _mark_complete(db, project, job, "error", error_msg)
            return
        except DBAPIError as exc:
            if db is not None:
                try:
                    db.rollback()
                except Exception:
                    pass
            if attempt < 5:
                _retry_database_connection(attempt, "recording scan failure", exc)
        except Exception:
            logger.exception("Could not record terminal state for scan %s", job_id)
            return
        finally:
            if db is not None:
                db.close()
    logger.error("Could not record terminal state for scan %s after database retries", job_id)


def _clear_previous_results(db: Session, project_id: uuid.UUID) -> None:
    from app.models import ArticleDraft, HubSpokeCluster, Keyword, KeywordBank, KeywordUrl, Url

    keyword_ids = select(Keyword.id).where(Keyword.project_id == project_id)
    url_ids = select(Url.id).where(Url.project_id == project_id)
    db.execute(delete(KeywordUrl).where(KeywordUrl.keyword_id.in_(keyword_ids)))
    db.execute(delete(KeywordUrl).where(KeywordUrl.url_id.in_(url_ids)))
    # Saved keywords and authored drafts must survive a rescan.
    db.execute(delete(Keyword).where(
        Keyword.project_id == project_id,
        ~Keyword.id.in_(select(KeywordBank.keyword_id)),
        ~Keyword.id.in_(select(ArticleDraft.keyword_id)),
    ))
    db.execute(delete(HubSpokeCluster).where(HubSpokeCluster.project_id == project_id))
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
        select(Url.id).where(Url.project_id == project_id, Url.url == url)
    ).scalar_one_or_none()
    if existing:
        db.execute(update(Url).where(Url.id == existing).values(scan_job_id=job_id))
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

    rows = db.execute(
        select(Url.url, Url.source_type)
        .where(Url.project_id == project_id, Url.status == "pending")
        .order_by(Url.url.asc())
    ).all()
    return sorted(rows, key=lambda row: (row.source_type != "own", row.url))


def _llm_filter_competitor_domains(
    seed_keywords: list[str],
    own_domain: str,
    candidates: list[dict[str, Any]],
    competitor_limit: int,
    audit_summary: str | None = None,
) -> list[str] | None:
    from nlp.openrouter import is_ai_configured
    if not candidates or not is_ai_configured():
        return None
    try:
        from nlp.openrouter import judge_competitor_domains

        judged = judge_competitor_domains(
            seed_keywords,
            own_domain,
            candidates[: settings.MAX_COMPETITOR_JUDGE_CANDIDATES],
            audit_summary=audit_summary,
            max_domains=competitor_limit,
        )
        if judged is None:
            return None
    except Exception as exc:
        logger.warning("Competitor LLM judge failed before request: %s", exc)
        return None

    candidate_by_root = {
        _registered_domain(item.get("domain")): item.get("domain")
        for item in candidates
        if _registered_domain(item.get("domain"))
    }
    accepted: list[str] = []
    for item in judged:
        domain = _origin(item.get("domain"))
        # The model may reject observed results, but it cannot discover or add
        # a domain that did not rank for an exact seed during this scan.
        candidate_domain = candidate_by_root.get(_registered_domain(domain))
        if candidate_domain and candidate_domain not in accepted:
            accepted.append(candidate_domain)
    if accepted:
        logger.info("Competitor LLM judge accepted %s domains", len(accepted))
    else:
        # An empty list is a successful strict judgment. Falling back here used
        # to reintroduce every domain the judge had explicitly rejected.
        logger.info("Competitor LLM judge rejected all direct-search candidates")
        return []

    signals = {item["domain"]: item for item in candidates if item.get("domain")}
    return _balanced_competitor_domains(
        accepted,
        signals,
        seed_keywords,
        competitor_limit,
    )


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


def _semantic_terms(seed_keywords: list[str], audit_summary: str | None = None) -> tuple[set[str], set[str]]:
    from nlp.openrouter import generate_core_domain_terms
    from nlp.keywords import (
        seed_keyword_terms,
        keyword_terms,
        site_scope_terms,
    )
    import asyncio
    import json

    fallback_topic_terms = seed_keyword_terms(seed_keywords)
    try:
        audit_data = json.loads(audit_summary) if audit_summary else {}
    except (TypeError, json.JSONDecodeError):
        audit_data = {}
    mechanical_scope = site_scope_terms(
        seed_keywords[0] if seed_keywords else "",
        audit_data if isinstance(audit_data, dict) else None,
    )
    fallback_topic_terms |= {f"__scope__{term}" for term in mechanical_scope}
    mechanical_negative_terms: set[str] = set()
    if isinstance(audit_data, dict):
        positive_terms = set(fallback_topic_terms) | mechanical_scope
        for field in ("primary_keyword", "industry_niche", "core_action", "capabilities", "content_opportunities"):
            raw = audit_data.get(field)
            values = raw if isinstance(raw, list) else [raw]
            for value in values:
                if isinstance(value, str):
                    positive_terms |= keyword_terms(value, min_len=3)
        boundaries = audit_data.get("hard_boundaries") or []
        if not isinstance(boundaries, list):
            boundaries = [boundaries]
        for boundary in boundaries:
            if isinstance(boundary, str):
                mechanical_negative_terms |= keyword_terms(boundary, min_len=3) - positive_terms
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    if loop.is_running():
        # In case we are already in an event loop, fallback to simple extraction
        return fallback_topic_terms, mechanical_negative_terms
        
    try:
        result = loop.run_until_complete(generate_core_domain_terms(seed_keywords, audit_summary))
        core_terms = set(result.get("core_terms", []))
        anchor_terms = set(result.get("anchor_terms", []))
        scope_terms = set(result.get("scope_terms", []))
        negative_terms = set(result.get("negative_terms", [])) | mechanical_negative_terms
        if core_terms or anchor_terms or scope_terms:
            marked = (
                core_terms
                | {f"__anchor__{term}" for term in anchor_terms}
                | {f"__scope__{term}" for term in (scope_terms | mechanical_scope)}
            )
            return marked, negative_terms
    except Exception as e:
        logger.error(f"Failed to generate dynamic semantic terms: {e}")

    # Fallback if LLM fails
    return fallback_topic_terms, mechanical_negative_terms


def _order_seeds_by_emd(seed_keywords: list[str], domain: str | None) -> list[str]:
    """Put the seed represented by the exact-match domain first."""
    if len(seed_keywords) < 2 or not domain:
        return seed_keywords
    registered = _registered_domain(domain) or domain
    host = urlparse(registered if "://" in registered else f"https://{registered}").hostname or ""
    label = host.lower().removeprefix("www.").split(".")[0]
    emd = re.sub(r"[^a-z0-9]", "", label)
    if not emd:
        return seed_keywords

    def affinity(seed: str) -> tuple[int, int]:
        compact = re.sub(r"[^a-z0-9]", "", seed.lower())
        exact = int(bool(compact) and (compact in emd or emd in compact))
        return exact, len(compact) if exact else 0

    return sorted(seed_keywords, key=affinity, reverse=True)


def _own_sitemap_keyword_phrases(
    db: Session,
    project_id: uuid.UUID,
    topic_terms: set[str] | None,
    negative_terms: set[str] | None,
) -> set[str]:
    from app.models import Url

    rows = db.execute(
        select(Url.url).where(Url.project_id == project_id, Url.source_type == "own")
    ).all()
    phrases: set[str] = set()
    for (url,) in rows:
        phrases.update(_url_keyword_candidates(url, topic_terms, negative_terms, include_single_terms=True))
    return phrases


def _own_content_keyword_phrases(
    db: Session,
    project_id: uuid.UUID,
    topic_terms: set[str] | None,
    negative_terms: set[str] | None,
) -> set[str]:
    from app.models import Url
    from nlp.keywords import extract_keywords_from_page

    query = select(Url.url, Url.scraped_text, Url.h1).where(Url.project_id == project_id, Url.source_type == "own")
    
    phrases: set[str] = set()
    for url, scraped_text, h1 in db.execute(query).yield_per(100):
        phrases.update(_url_keyword_candidates(url, topic_terms, negative_terms, include_single_terms=True))
        if not scraped_text:
            continue
        keyword_result = extract_keywords_from_page(
            scraped_text,
            h1=h1,
            use_keybert=settings.ENABLE_KEYBERT,
            use_spacy=settings.ENABLE_SPACY,
        )
        phrases.update(_keyword_phrases(keyword_result, min_words=1))

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
    negative_terms: set[str] | None,
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
            if is_publishable_keyword(phrase, min_words=2, topic_terms=topic_terms, negative_terms=negative_terms):
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
    negative_terms: set[str] | None,
) -> None:
    for phrase in _url_keyword_candidates(url, topic_terms, negative_terms, include_single_terms=False):
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
    negative_terms: set[str] | None = None,
) -> None:
    from nlp.keywords import clean_phrase, is_publishable_keyword

    def add_keyword(phrase: str, keyword_type: str, score: float = 1.0) -> None:
        key = clean_phrase(phrase)
        if not is_publishable_keyword(key, min_words=2, topic_terms=topic_terms, negative_terms=negative_terms):
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


def _build_tiered_accumulator(
    acc: dict[str, dict[str, Any]],
    tier_results: list[dict],
    original_extracted: list[dict[str, Any]],
) -> None:
    """
    Translate classify_keyword_tiers() output into the accumulator dict
    expected by _store_keywords(). Mutates `acc` in place.
    """
    # Build a lookup from phrase -> url_ids from the original AI extraction
    phrase_url_map: dict[str, set] = {}
    for item in original_extracted:
        phrase = str(item.get("phrase", "")).strip().lower()
        if phrase:
            url_ids = set()
            for uid in item.get("url_ids", []):
                try:
                    url_ids.add(uuid.UUID(uid) if isinstance(uid, str) else uid)
                except (ValueError, AttributeError):
                    pass
            phrase_url_map.setdefault(phrase, set()).update(url_ids)

    def _base_entry(kw: dict, tier: str, sub_silo: int, **extra) -> dict:
        phrase = kw["phrase"]
        entry = {
            "type": kw.get("type", "primary"),
            "count": 1,
            "url_ids": phrase_url_map.get(phrase, set()),
            "score": 1.0,
            "source": "sitemap",
            "tier": tier,
            "sub_silo_id": sub_silo,
        }
        entry.update(extra)
        return entry

    for tier_rec in tier_results:
        tier = tier_rec["tier"]
        sub_silo = tier_rec.get("sub_silo", 0)

        if tier == "merge":
            rep = tier_rec["representative_keyword"]
            phrase = rep["phrase"]
            dropped = [kw["phrase"] for kw in tier_rec["cluster"] if kw["phrase"] != phrase]
            # Collect url_ids from all merged phrases
            all_url_ids: set = set()
            for kw in tier_rec["cluster"]:
                all_url_ids.update(phrase_url_map.get(kw["phrase"], set()))
            entry = _base_entry(rep, "merge", sub_silo, merged_from=dropped)
            entry["url_ids"] = all_url_ids
            entry["count"] = len(tier_rec["cluster"])
            if phrase not in acc:
                acc[phrase] = entry
            else:
                acc[phrase]["url_ids"].update(all_url_ids)
                acc[phrase]["merged_from"] = dropped

        elif tier == "subheading_group":
            broadest = tier_rec["broadest"]
            phrase = broadest["phrase"]
            h_tags = [kw["phrase"] for kw in tier_rec["cluster"] if kw["phrase"] != phrase]
            all_url_ids = set()
            for kw in tier_rec["cluster"]:
                all_url_ids.update(phrase_url_map.get(kw["phrase"], set()))
            entry = _base_entry(
                broadest, "subheading_group", sub_silo,
                article_title=phrase,
                h_tags=h_tags,
            )
            entry["url_ids"] = all_url_ids
            entry["count"] = len(tier_rec["cluster"])
            if phrase not in acc:
                acc[phrase] = entry
            else:
                acc[phrase]["url_ids"].update(all_url_ids)
                acc[phrase]["h_tags"] = h_tags
                acc[phrase]["article_title"] = phrase

        elif tier == "related":
            group_id = tier_rec.get("cluster_group_id", "")
            for kw in tier_rec.get("members", []):
                phrase = kw["phrase"]
                entry = _base_entry(kw, "related", sub_silo, cluster_group_id=group_id)
                if phrase not in acc:
                    acc[phrase] = entry
                else:
                    acc[phrase]["url_ids"].update(entry["url_ids"])
                    acc[phrase]["cluster_group_id"] = group_id

        elif tier == "outlier":
            kw = tier_rec["keyword"]
            phrase = kw["phrase"]
            entry = _base_entry(kw, "outlier", sub_silo)
            if phrase not in acc:
                acc[phrase] = entry
            else:
                acc[phrase]["url_ids"].update(entry["url_ids"])


def _remove_covered_keywords(accumulator: dict[str, dict[str, Any]], own_keyword_phrases: set[str]) -> None:
    if not own_keyword_phrases:
        return

    own_term_sets = [_phrase_terms(phrase) for phrase in own_keyword_phrases]
    own_term_sets = [terms for terms in own_term_sets if terms]
    own_term_frozensets = {frozenset(terms) for terms in own_term_sets}

    for phrase in list(accumulator.keys()):
        if phrase in own_keyword_phrases:
            del accumulator[phrase]
            continue

        phrase_terms = frozenset(_phrase_terms(phrase))
        if phrase_terms and phrase_terms in own_term_frozensets:
            del accumulator[phrase]


def _phrase_terms(phrase: str) -> set[str]:
    from nlp.keywords import STOPWORDS

    return {word for word in phrase.split() if word not in STOPWORDS and len(word) > 2}


def _keyword_matches_topic(
    phrase: str,
    seed_keywords: list[str],
    topic_terms: set[str] | None,
    negative_terms: set[str] | None,
) -> bool:
    """Deterministic relevance fence applied after extraction and AI rewriting."""
    from nlp.keywords import is_topic_relevant_keyword
    return is_topic_relevant_keyword(phrase, seed_keywords, topic_terms, negative_terms)


def _ensure_minimum_keyword_count(
    db: Session,
    project_id: uuid.UUID,
    seed_keywords: list[str],
    topic_terms: set[str] | None,
    negative_terms: set[str] | None,
    audit_summary: str | None,
    generate_keywords: Any,
    ai_generated_source: Any,
    evidence_phrases: list[str] | None = None,
) -> int:
    """Pursue the configured research goal without padding unsupported results."""
    from app.models import Keyword, KeywordUrl, Url
    from nlp.keywords import clean_phrase

    target = max(100, int(settings.MIN_KEYWORDS_PER_SCAN))
    existing = {
        clean_phrase(row[0])
        for row in db.execute(select(Keyword.phrase).where(Keyword.project_id == project_id)).all()
    }
    own_phrases = _own_content_keyword_phrases(db, project_id, topic_terms, negative_terms)
    excluded = existing | own_phrases
    ai_url_str, ai_source_domain = ai_generated_source()
    ai_url = db.execute(
        select(Url).where(Url.project_id == project_id, Url.url == ai_url_str)
    ).scalar_one_or_none()
    if not ai_url:
        ai_url = Url(
            project_id=project_id,
            url=ai_url_str,
            source_type="ai",
            source_domain=ai_source_domain,
            status="scraped",
        )
        db.add(ai_url)
        db.flush()

    ai_existing = set(db.execute(
        select(Keyword.phrase)
        .join(KeywordUrl, KeywordUrl.keyword_id == Keyword.id)
        .where(Keyword.project_id == project_id, KeywordUrl.url_id == ai_url.id)
    ).scalars().all())
    # Always add 60 audit-supported easy wins even when paid/scraped sources
    # already bring the project above the overall keyword target.
    minimum_ai_keywords = 60

    for batch_number in range(max(1, int(settings.AI_KEYWORD_GENERATION_MAX_BATCHES))):
        missing = max(target - len(existing), minimum_ai_keywords - len(ai_existing))
        if missing <= 0:
            break
        requested = min(max(5, int(settings.AI_KEYWORD_GENERATION_BATCH_SIZE)), max(missing + 10, 20))
        generated = generate_keywords(
            seed_keywords,
            topic_terms=topic_terms,
            negative_terms=negative_terms,
            audit_summary=audit_summary,
            apply_gap_filter=False,
            target_count=requested,
            exclude_phrases=excluded,
            evidence_phrases=evidence_phrases,
        ) or []

        accumulator: dict[str, dict[str, Any]] = {}
        for item in generated:
            phrase = clean_phrase(str(item.get("phrase") or ""))
            if not phrase or phrase in excluded:
                continue
            if not _keyword_matches_topic(phrase, seed_keywords, topic_terms, negative_terms):
                continue
            accumulator[phrase] = {
                "type": item.get("type", "long-tail"),
                "count": 1,
                "url_ids": {ai_url.id},
                "score": 1.0,
                "source": "sitemap_ai",
                "tier": "outlier",
            }

        if accumulator:
            _store_keywords(db, project_id, accumulator)
            existing.update(accumulator)
            ai_existing.update(accumulator)
            excluded.update(accumulator)
            logger.info(
                "[%s] AI keyword expansion batch %s stored %s; total is %s/%s with %s AI recommendations",
                project_id,
                batch_number + 1,
                len(accumulator),
                len(existing),
                target,
                len(ai_existing),
            )
        else:
            logger.warning("[%s] Keyword expansion batch %s returned no new relevant phrases", project_id, batch_number + 1)

    final_count = db.execute(
        select(func.count(Keyword.id)).where(Keyword.project_id == project_id)
    ).scalar_one()
    if final_count == 0:
        # Search providers, competitor sites, or the AI provider can all be
        # temporarily unavailable. Gold Hunter seeds are still verified user
        # inputs and provide a truthful baseline without invented variants.
        baseline: dict[str, dict[str, Any]] = {}
        for raw_seed in seed_keywords:
            phrase = clean_phrase(raw_seed)
            if not phrase:
                continue
            baseline[phrase] = {
                "type": "primary",
                "count": 1,
                "url_ids": {ai_url.id},
                "score": 1.0,
                "source": "sitemap_ai",
                "tier": "outlier",
            }
        if baseline:
            _store_keywords(db, project_id, baseline)
            final_count = db.execute(
                select(func.count(Keyword.id)).where(Keyword.project_id == project_id)
            ).scalar_one()
            logger.warning(
                "[%s] External keyword enrichment returned no results; retained %s verified seed keywords.",
                project_id,
                final_count,
            )
    if final_count < target:
        if final_count == 0:
            raise RuntimeError(
                "No keyword gaps could be generated. Check the AI provider configuration and whether competitor pages can be reached, then retry."
            )
        logger.warning(
            "[%s] Produced %s evidence-backed keywords (research goal %s). Refusing to pad the result with unsupported variants.",
            project_id,
            final_count,
            target,
        )
    return final_count


def _refine_keyword_gap_recommendations(
    db: Session,
    project_id: uuid.UUID,
    seed_keywords: list[str],
    accumulator: dict[str, dict[str, Any]],
    topic_terms: set[str] | None,
    negative_terms: set[str] | None,
    audit_summary: str | None = None,
) -> dict[str, dict[str, Any]]:
    if not accumulator:
        return accumulator

    candidate_rows = _keyword_gap_candidate_rows(db, project_id, accumulator, topic_terms, negative_terms)
    if not candidate_rows:
        return {}

    try:
        from nlp.openrouter import filter_keyword_gap_recommendations

        ai_recommendations = filter_keyword_gap_recommendations(
            seed_keywords,
            candidate_rows,
            audit_summary=audit_summary,
            max_keywords=settings.AI_KEYWORD_GAP_RESULT_LIMIT,
        )
    except Exception as exc:
        logger.warning("AI keyword gap filter failed before request: %s", exc)
        ai_recommendations = None

    if ai_recommendations is not None:
        refined = _build_ai_refined_accumulator(
            accumulator,
            ai_recommendations,
            topic_terms,
            negative_terms,
        )
        if refined:
            logger.info("AI keyword gap filter kept %s of %s candidates", len(refined), len(accumulator))
            return refined
        else:
            logger.info("AI keyword gap filter correctly rejected all %s candidates", len(accumulator))
            return {}

    fallback = _build_heuristic_gap_accumulator(accumulator, candidate_rows, topic_terms, negative_terms)
    logger.info("Heuristic keyword gap filter kept %s of %s candidates", len(fallback), len(accumulator))
    return fallback


def _keyword_gap_candidate_rows(
    db: Session,
    project_id: uuid.UUID,
    accumulator: dict[str, dict[str, Any]],
    topic_terms: set[str] | None,
    negative_terms: set[str] | None,
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
        score = _gap_candidate_score(phrase, data, domains, topic_terms, negative_terms)
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
    negative_terms: set[str] | None,
) -> float:
    terms = _phrase_terms(phrase)
    word_count = len(phrase.split())
    frequency = int(data.get("count", 1))
    domain_count = len(domains)
    score = frequency * 2.0 + domain_count * 4.0
    if topic_terms:
        score += len(terms & topic_terms) * 3.0
    if negative_terms:
        score -= len(terms & negative_terms) * 10.0
    if 2 <= word_count <= 5:
        score += 2.0
    if frequency <= 1 and domain_count <= 1:
        score -= 0.5
    return score


def _build_ai_refined_accumulator(
    accumulator: dict[str, dict[str, Any]],
    ai_recommendations: list[dict[str, Any]],
    topic_terms: set[str] | None,
    negative_terms: set[str] | None,
) -> dict[str, dict[str, Any]]:
    from nlp.keywords import clean_phrase, is_publishable_keyword, check_intent_cannibalization
    from nlp.openrouter import normalize_keyword_type

    source_lookup = {clean_phrase(phrase): data for phrase, data in accumulator.items()}
    refined: dict[str, dict[str, Any]] = {}
    seen_phrases: list[str] = []

    for index, item in enumerate(ai_recommendations):
        source_phrase = clean_phrase(str(item.get("source_phrase", "")))
        phrase = clean_phrase(str(item.get("phrase", "")))
        keyword_type = normalize_keyword_type(item.get("type"))
        
        if source_phrase not in source_lookup and phrase in source_lookup:
            source_phrase = phrase
            
        source_data = source_lookup.get(source_phrase)
        if not source_data or not is_publishable_keyword(phrase, min_words=2, topic_terms=topic_terms, negative_terms=negative_terms):
            continue

        # Check against all previously seen phrases for cannibalization (subsets or high jaccard)
        is_cannibalized = False
        target_merge_phrase = None
        for seen in seen_phrases:
            if check_intent_cannibalization(phrase, seen):
                is_cannibalized = True
                target_merge_phrase = seen
                break

        if is_cannibalized and target_merge_phrase:
            # Merge this item's metrics into the existing approved phrase
            refined[target_merge_phrase]["count"] += int(source_data.get("count", 1))
            refined[target_merge_phrase]["url_ids"].update(source_data.get("url_ids", set()))
            continue

        seen_phrases.append(phrase)

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
    topic_terms: set[str] | None,
    negative_terms: set[str] | None,
) -> dict[str, dict[str, Any]]:
    limit = max(1, settings.AI_KEYWORD_GAP_RESULT_LIMIT)
    
    if topic_terms:
        filtered_candidates = [
            row for row in candidate_rows
            if _phrase_terms(row["phrase"]) & topic_terms
        ]
    else:
        filtered_candidates = candidate_rows
        
    kept_phrases = {row["phrase"] for row in filtered_candidates[:limit]}
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
                    search_volume=data.get("search_volume"),
                    difficulty=data.get("difficulty"),
                )
                db.add(keyword)
                db.flush()
            else:
                keyword.frequency += data["count"]
                keyword.updated_at = datetime.utcnow()
                if data.get("search_volume") is not None:
                    keyword.search_volume = data["search_volume"]
                if data.get("difficulty") is not None:
                    keyword.difficulty = data["difficulty"]

            # Persist 4-tier classification metadata if present
            if data.get("tier"):
                keyword.tier = data["tier"]
            if data.get("sub_silo_id") is not None:
                keyword.sub_silo_id = data["sub_silo_id"]
            if data.get("cluster_group_id"):
                keyword.cluster_group_id = data["cluster_group_id"]
            if data.get("article_title"):
                keyword.article_title = data["article_title"]
            if data.get("h_tags"):
                keyword.h_tags = data["h_tags"]
            if data.get("merged_from"):
                keyword.merged_from = data["merged_from"]

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
        .where(Url.project_id == project.id, ~Url.source_type.in_(["ai", "provider"]))
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
