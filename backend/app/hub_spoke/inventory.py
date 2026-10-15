"""Build planning inputs from research, gaps, owned pages and the site's main topic."""
from urllib.parse import unquote, urlparse
from sqlalchemy import select
from app.models import Keyword, KeywordUrl, ResearchKeyword, Url
from nlp.hub_spoke_agent import normalize_keyword_records, MAX_ARCHITECTURE_KEYWORDS
from nlp.keywords import clean_phrase, is_publishable_keyword


async def project_planning_inventory(db, project, primary_keyword=""):
    keywords = list((await db.execute(select(Keyword).where(Keyword.project_id == project.id)
                                     .order_by(Keyword.frequency.desc(), Keyword.created_at.asc()).limit(5000))).scalars())
    sources = (await db.execute(select(KeywordUrl.keyword_id, Url.url).join(Url, Url.id == KeywordUrl.url_id).where(
        Url.project_id == project.id, Url.source_type == "competitor",
    ))).all()
    domains = {}
    for keyword_id, url in sources:
        if urlparse(url).hostname:
            domains.setdefault(keyword_id, set()).add(urlparse(url).hostname)
    gaps = [{"phrase": row.phrase, "type": row.keyword_type, "search_volume": row.search_volume,
             "difficulty": row.difficulty, "frequency": row.frequency,
             "source_domains": sorted(domains.get(row.id, set())), "seo_recommendation": row.seo_recommendation}
            for row in keywords]
    research = list((await db.execute(select(ResearchKeyword).where(
        ResearchKeyword.project_id == project.id, ResearchKeyword.review_status != "rejected",
    ).order_by(ResearchKeyword.phrase).limit(5000))).scalars())
    reviewed, pending = [], []
    for row in research:
        evidence = row.payload.get("evidence") or {}
        editorial = isinstance(evidence, dict) and evidence.get("kind") == "editorial_inference"
        item = {**row.payload, "phrase": row.phrase, "research_status": row.review_status,
                "evidence_type": "editorial_proposal" if editorial else (
                    "research_candidate" if row.review_status == "pending" else "reviewed_research")}
        if editorial:
            item["seo_recommendation"] = (
                f"Editorial idea based on: {str(evidence.get('excerpt') or '')[:600]}. "
                "This is not an observed search query or proof of demand. "
                + str(item.get("seo_recommendation") or "")
            )
        (pending if row.review_status == "pending" else reviewed).append(item)
    owned = []
    pages = (await db.execute(select(Url.url, Url.h1).where(
        Url.project_id == project.id, Url.source_type == "own",
    ).order_by(Url.url))).all()
    for url, title in pages:
        phrase = title or unquote(urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]).replace("-", " ").replace("_", " ")
        if is_publishable_keyword(phrase, min_words=2):
            owned.append({"phrase": phrase, "type": "heading", "evidence_type": "owned_page",
                          "research_status": "covered", "source_urls": [url],
                          "seo_recommendation": f"Existing page: {url}. Reuse its URL; verify content before proposing improvements."})
    primary = clean_phrase(primary_keyword or (project.target_keywords or [""])[0])
    records = normalize_keyword_records([*gaps, *reviewed, *pending, *owned], primary)
    by_phrase = {item["phrase"]: item for item in records}
    # Bound architecture size without letting one source crowd out every other.
    selected = [primary] if primary in by_phrase else []
    seen = set(selected)
    buckets = [gaps, owned, reviewed, pending]
    for index in range(max((len(group) for group in buckets), default=0)):
        for group in buckets:
            if index >= len(group) or len(selected) >= MAX_ARCHITECTURE_KEYWORDS:
                continue
            phrase = clean_phrase(str(group[index]["phrase"]))
            if phrase in by_phrase and phrase not in seen:
                selected.append(phrase)
                seen.add(phrase)
    summary = {"new_gaps": len(gaps), "research_candidates": len(research),
               "pending_review": len(pending), "existing_topics": len(owned),
               "planning_keywords": len(selected), "available_keywords": len(records),
               "not_included": len(records) - len(selected)}
    return [by_phrase[phrase] for phrase in selected], summary
