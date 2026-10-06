"""Attach server-owned crawl evidence to a topical architecture request."""
import json
from sqlalchemy import select
from app.models import Url


async def context_with_owned_pages(db, project_id, context):
    try:
        payload = json.loads(context) if context else {}
    except (ValueError, TypeError):
        payload = {'audit_summary': context}
    if not isinstance(payload, dict):
        payload = {'audit_summary': context}
    rows = await db.execute(select(Url.url, Url.h1, Url.scraped_text).where(
        Url.project_id == project_id, Url.source_type == 'own',
    ).order_by(Url.url))
    supplied = payload.get('owned_pages', [])
    pages = {page['url']: page for page in supplied
             if isinstance(page, dict) and isinstance(page.get('url'), str)} if isinstance(supplied, list) else {}
    # Keep every known owned URL and title. Only excerpts are bounded: pages
    # beyond the first 30 (or awaiting scraping) still exist on the user's site.
    pages.update({url: {'url': url, 'title': h1 or '',
                       'text_excerpt': (text or '')[:3000] if index < 30 else '',
                       'evidence': 'owned_crawl'}
                  for index, (url, h1, text) in enumerate(rows.all())})
    payload['owned_pages'] = list(pages.values())
    payload['owned_coverage_note'] = 'All known owned URLs and titles; bounded text excerpts. An absent topic is not proof of absence from the whole site.'
    return json.dumps(payload)
