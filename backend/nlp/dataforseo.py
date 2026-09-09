"""Budget-capped DataForSEO keyword research with persistent response caching."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

import requests
from sqlalchemy.orm import Session

from app.config import settings

logger = logging.getLogger(__name__)
BASE_URL = "https://api.dataforseo.com/v3"
ESTIMATED_REQUEST_COST = 0.015


@dataclass
class KeywordResearchResult:
    keywords: list[dict[str, Any]]
    spent: float
    requests: int
    cache_hits: int


def _credentials() -> tuple[str, str]:
    return (
        settings.DATAFORSEO_LOGIN or settings.DATAFORSEO_API_LOGIN,
        settings.DATAFORSEO_PASSWORD or settings.DATAFORSEO_API_PASSWORD,
    )


def is_dataforseo_configured() -> bool:
    return all(_credentials())


def _cache_key(endpoint: str, payload: dict[str, Any]) -> str:
    encoded = json.dumps([endpoint, payload], sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _cached_response(db: Session, key: str) -> dict[str, Any] | None:
    from app.models import KeywordResearchCache

    row = db.get(KeywordResearchCache, key)
    if not row:
        return None
    expiry = row.expires_at
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if expiry <= datetime.now(timezone.utc):
        db.delete(row)
        db.commit()
        return None
    return row.response_data


def _store_cached_response(db: Session, key: str, response: dict[str, Any], cost: float) -> None:
    from app.models import KeywordResearchCache

    expires_at = datetime.now(timezone.utc) + timedelta(days=max(1, settings.DATAFORSEO_CACHE_DAYS))
    row = db.get(KeywordResearchCache, key)
    if row:
        row.response_data = response
        row.request_cost = cost
        row.expires_at = expires_at
    else:
        db.add(KeywordResearchCache(
            cache_key=key,
            response_data=response,
            request_cost=cost,
            expires_at=expires_at,
        ))
    db.commit()


def _request(db: Session, endpoint: str, payload: dict[str, Any]) -> tuple[dict[str, Any], float, bool]:
    key = _cache_key(endpoint, payload)
    cached = _cached_response(db, key)
    if cached is not None:
        return cached, 0.0, True

    login, password = _credentials()
    response = requests.post(
        f"{BASE_URL}/{endpoint}",
        auth=(login, password),
        json=[payload],
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    if int(data.get("status_code") or 0) != 20000:
        raise RuntimeError(data.get("status_message") or "DataForSEO request failed")
    tasks = data.get("tasks") or []
    failed = [task for task in tasks if int(task.get("status_code") or 0) != 20000]
    if failed:
        raise RuntimeError(failed[0].get("status_message") or "DataForSEO task failed")
    cost = float(data.get("cost") or sum(float(task.get("cost") or 0) for task in tasks))
    _store_cached_response(db, key, data, cost)
    return data, cost, False


def _walk_keyword_items(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        keyword = value.get("keyword")
        if isinstance(keyword, str) and (
            "keyword_info" in value or "keyword_properties" in value or "search_intent_info" in value
        ):
            yield value
        for nested in value.values():
            yield from _walk_keyword_items(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_keyword_items(nested)


def _normalize_items(response: dict[str, Any]) -> list[dict[str, Any]]:
    from nlp.keywords import clean_phrase

    normalized: dict[str, dict[str, Any]] = {}
    for item in _walk_keyword_items(response.get("tasks") or []):
        phrase = clean_phrase(item.get("keyword") or "")
        if not phrase:
            continue
        info = item.get("keyword_info") or {}
        properties = item.get("keyword_properties") or {}
        intent_info = item.get("search_intent_info") or {}
        volume = info.get("search_volume")
        difficulty = properties.get("keyword_difficulty")
        normalized[phrase] = {
            "phrase": phrase,
            "type": "long-tail" if len(phrase.split()) >= 3 else "primary",
            "search_volume": int(volume) if isinstance(volume, (int, float)) else None,
            "difficulty": float(difficulty) if isinstance(difficulty, (int, float)) else None,
            "intent": intent_info.get("main_intent"),
            "source": "dataforseo",
        }
    return list(normalized.values())


def collect_keyword_research(
    db: Session,
    domain: str,
    seed_keywords: list[str],
) -> KeywordResearchResult:
    """Collect all seed ideas in one call, then domain keywords if budget remains."""
    if not is_dataforseo_configured():
        return KeywordResearchResult([], 0.0, 0, 0)

    base = {
        "limit": max(25, min(500, settings.DATAFORSEO_RESULT_LIMIT)),
        "include_serp_info": False,
        "include_clickstream_data": False,
    }
    if settings.DATAFORSEO_LOCATION_CODE:
        base["location_code"] = settings.DATAFORSEO_LOCATION_CODE
    else:
        base["location_name"] = settings.DATAFORSEO_DEFAULT_LOCATION
    if settings.DATAFORSEO_LANGUAGE_CODE:
        base["language_code"] = settings.DATAFORSEO_LANGUAGE_CODE
    else:
        base["language_name"] = settings.DATAFORSEO_DEFAULT_LANGUAGE
    requests_to_make: list[tuple[str, dict[str, Any]]] = []
    if seed_keywords:
        requests_to_make.append((
            "dataforseo_labs/google/keyword_ideas/live",
            {**base, "keywords": seed_keywords[:200], "closely_variants": False},
        ))
    if domain:
        requests_to_make.append((
            "dataforseo_labs/google/keywords_for_site/live",
            {**base, "target": domain, "include_subdomains": True},
        ))

    spent = 0.0
    request_count = 0
    cache_hits = 0
    collected: dict[str, dict[str, Any]] = {}
    cap = max(0.01, float(settings.DATAFORSEO_MAX_COST_PER_SCAN))

    for endpoint, payload in requests_to_make:
        # Cached calls cost nothing. For an uncached call, reserve a conservative
        # estimated amount before sending so a small prepaid balance is safe.
        key = _cache_key(endpoint, payload)
        cached = _cached_response(db, key)
        if cached is None and spent + ESTIMATED_REQUEST_COST > cap:
            logger.warning("DataForSEO scan budget reached at $%.4f (cap $%.4f)", spent, cap)
            break
        try:
            if cached is not None:
                response, cost, was_cached = cached, 0.0, True
            else:
                response, cost, was_cached = _request(db, endpoint, payload)
            request_count += 0 if was_cached else 1
            cache_hits += 1 if was_cached else 0
            spent += cost
            for item in _normalize_items(response):
                existing = collected.get(item["phrase"])
                if not existing or (item.get("search_volume") or 0) > (existing.get("search_volume") or 0):
                    collected[item["phrase"]] = item
            if spent >= cap:
                break
        except Exception as exc:
            logger.warning("DataForSEO %s failed: %s", endpoint.rsplit("/", 2)[-2], exc)

    logger.info(
        "DataForSEO collected %s keywords using %s paid requests, %s cache hits, $%.4f",
        len(collected), request_count, cache_hits, spent,
    )
    return KeywordResearchResult(list(collected.values()), spent, request_count, cache_hits)
