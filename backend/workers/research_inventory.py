"""Keep sourced and editorial research without counting every candidate as a gap."""
import json
import uuid
from urllib.parse import urlparse

from sqlalchemy import select
from app.models import ResearchKeyword, Url
from nlp.keywords import clean_phrase, is_publishable_keyword


def remember_candidates(db, project_id, candidates, source):
    existing = {row.phrase: row for row in db.execute(
        select(ResearchKeyword).where(ResearchKeyword.project_id == project_id)
    ).scalars()}
    url_ids = set()
    for item in candidates:
        for value in item.get("url_ids", []):
            try:
                url_ids.add(uuid.UUID(str(value)))
            except (ValueError, TypeError):
                pass
    urls = {str(row.id): row for row in db.execute(select(Url).where(
        Url.project_id == project_id, Url.id.in_(url_ids),
    )).scalars()} if url_ids else {}
    for item in candidates[:1000]:
        phrase = clean_phrase(str(item.get("phrase") or ""))
        if not is_publishable_keyword(phrase, min_words=2):
            continue
        row = existing.get(phrase)
        if row is None:
            row = ResearchKeyword(project_id=project_id, phrase=phrase, review_status="pending", payload={})
            db.add(row)
            existing[phrase] = row
        previous = row.payload or {}
        payload = json.loads(json.dumps(item, default=str))
        linked = [urls[str(value)] for value in item.get("url_ids", []) if str(value) in urls]
        payload["source_domains"] = list(dict.fromkeys([
            *previous.get("source_domains", []),
            *(urlparse(page.url).hostname for page in linked if page.source_type == "competitor" and urlparse(page.url).hostname),
        ]))
        evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
        payload["source_urls"] = list(dict.fromkeys([
            *previous.get("source_urls", []), *(page.url for page in linked),
            *([evidence["url"]] if isinstance(evidence.get("url"), str) else []),
        ]))[:20]
        payload["research_sources"] = list(dict.fromkeys([*previous.get("research_sources", []), source]))
        for metric in ("search_volume", "difficulty"):
            if payload.get(metric) is None and previous.get(metric) is not None:
                payload[metric] = previous[metric]
        row.payload = {**previous, **payload, "phrase": phrase}
    db.commit()


def record_review(db, project_id, decisions, accepted=()):
    """Only explicit verdicts change status; omissions stay pending for the architect."""
    records = {row.phrase: row for row in db.execute(
        select(ResearchKeyword).where(ResearchKeyword.project_id == project_id)
    ).scalars()}
    # Accepted rows also cover adapters that do not emit a separate decision log.
    for item in [*({**item, "decision": "keep"} for item in accepted or []), *decisions]:
        source = clean_phrase(str(item.get("source_phrase") or item.get("phrase") or ""))
        row = records.get(source)
        status = {"keep": "opportunity", "covered": "covered", "reject": "rejected"}.get(item.get("decision"))
        if row is None or status is None:
            continue
        row.review_status = status
        row.payload = {**row.payload,
                       "seo_recommendation": item.get("review_reason") or item.get("reason"),
                       "opportunity": item.get("opportunity")}
    db.commit()
