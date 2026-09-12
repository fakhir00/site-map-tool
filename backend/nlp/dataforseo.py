"""Budget-capped DataForSEO keyword research with persistent response caching."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

import requests
from sqlalchemy.orm import Session

from app.config import settings

logger = logging.getLogger(__name__)
BASE_URL = "https://api.dataforseo.com/v3"
ESTIMATED_REQUEST_COST = 0.015
MAX_CONSERVATIVE_SCAN_COST = 0.08


def _research_seeds(seed_keywords: list[str], audit_summary: str | None) -> list[str]:
    """Use only user-approved Gold Hunter seeds for paid keyword expansion.

    The audit describes the site and is valuable when rejecting candidates. It
    is not a safe provider query source: capability sentences such as "compare
    lunar and solar age" can make a keyword API expand into the solar system.
    """
    from nlp.keywords import normalize_seed_keywords

    _ = audit_summary
    return normalize_seed_keywords(seed_keywords)[:200]


@dataclass
class KeywordResearchResult:
    keywords: list[dict[str, Any]]
    spent: float
    requests: int
    cache_hits: int
    errors: list[str] = field(default_factory=list)


def _credentials() -> tuple[str, str]:
    """Select one complete credential pair; never mix fields across accounts."""
    primary = (settings.DATAFORSEO_LOGIN.strip(), settings.DATAFORSEO_PASSWORD.strip())
    alias = (settings.DATAFORSEO_API_LOGIN.strip(), settings.DATAFORSEO_API_PASSWORD.strip())
    if all(primary):
        return primary
    if all(alias):
        return alias
    return "", ""


def _credential_source() -> str | None:
    login, password = _credentials()
    if not login or not password:
        return None
    if login == settings.DATAFORSEO_LOGIN.strip() and password == settings.DATAFORSEO_PASSWORD.strip():
        return "DATAFORSEO_LOGIN"
    return "DATAFORSEO_API_LOGIN"


def is_dataforseo_configured() -> bool:
    return all(_credentials())


def _cache_key(endpoint: str, payload: dict[str, Any]) -> str:
    # Account changes must not reuse another account's cached provider response.
    login, _password = _credentials()
    account_key = hashlib.sha256(login.lower().encode()).hexdigest()[:16] if login else "unconfigured"
    encoded = json.dumps([account_key, endpoint, payload], sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


_STATUS_CACHE: tuple[float, dict[str, Any]] | None = None


def dataforseo_account_status(force: bool = False) -> dict[str, Any]:
    """Verify account authentication using the non-task account endpoint."""
    global _STATUS_CACHE
    now = time.monotonic()
    if not force and _STATUS_CACHE and now - _STATUS_CACHE[0] < 300:
        return dict(_STATUS_CACHE[1])

    login, password = _credentials()
    source = _credential_source()
    if not login or not password:
        result = {
            "configured": False,
            "authenticated": False,
            "credential_source": None,
            "message": "Add one complete DataForSEO login and password pair in Render.",
        }
        _STATUS_CACHE = (now, result)
        return dict(result)

    try:
        response = requests.get(
            f"{BASE_URL}/appendix/user_data",
            auth=(login, password),
            timeout=10,
        )
        if response.status_code == 401:
            result = {
                "configured": True,
                "authenticated": False,
                "credential_source": source,
                "message": "DataForSEO rejected the selected login or password.",
            }
        else:
            response.raise_for_status()
            payload = response.json()
            authenticated = int(payload.get("status_code") or 0) == 20000
            result = {
                "configured": True,
                "authenticated": authenticated,
                "credential_source": source,
                "message": "Connected to DataForSEO." if authenticated else str(
                    payload.get("status_message") or "DataForSEO account check failed."
                )[:200],
            }
    except Exception as exc:
        result = {
            "configured": True,
            "authenticated": False,
            "credential_source": source,
            "message": f"Could not reach DataForSEO: {type(exc).__name__}",
        }
    _STATUS_CACHE = (now, result)
    return dict(result)


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
    audit_summary: str | None = None,
) -> KeywordResearchResult:
    """Collect ideas for every exact seed in one budget-capped request."""
    if not is_dataforseo_configured():
        return KeywordResearchResult([], 0.0, 0, 0)

    base = {
        # One focused request per scan, with a hard result ceiling even if an
        # old Render environment variable still contains the former 500 value.
        "limit": max(25, min(200, settings.DATAFORSEO_RESULT_LIMIT)),
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
    research_seeds = _research_seeds(seed_keywords, audit_summary)
    if research_seeds:
        per_seed_limit = max(25, min(75, int(base["limit"])))
        for seed in research_seeds[:5]:
            requests_to_make.append((
                "dataforseo_labs/google/keyword_suggestions/live",
                {
                    **base,
                    "limit": per_seed_limit,
                    "keyword": seed,
                    "exact_match": True,
                    "include_seed_keyword": True,
                    "ignore_synonyms": False,
                    "filters": [["keyword_info.search_volume", ">", 0]],
                    "order_by": [
                        "keyword_properties.keyword_difficulty,asc",
                        "keyword_info.search_volume,desc",
                    ],
                },
            ))
    # A domain can rank for stale, accidental, or mixed-topic queries. Importing
    # that footprint polluted focused EMD research and spent a second API call.
    _ = domain

    spent = 0.0
    request_count = 0
    cache_hits = 0
    collected: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    cap = min(
        MAX_CONSERVATIVE_SCAN_COST,
        max(0.01, float(settings.DATAFORSEO_MAX_COST_PER_SCAN)),
    )

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
            message = str(exc)[:300]
            errors.append(message)
            logger.warning("DataForSEO %s failed: %s", endpoint.rsplit("/", 2)[-2], message)

    logger.info(
        "DataForSEO collected %s keywords using %s paid requests, %s cache hits, $%.4f",
        len(collected), request_count, cache_hits, spent,
    )
    return KeywordResearchResult(list(collected.values()), spent, request_count, cache_hits, errors)


def search_competitors(
    db: Session,
    keyword: str,
    locale: str = "us",
    max_results: int = 10,
) -> list[dict[str, Any]]:
    """Return exact-query organic competitors through one cached low-cost call."""
    if not is_dataforseo_configured() or not keyword.strip():
        return []

    payload: dict[str, Any] = {
        "keyword": keyword.strip(),
        "device": "desktop",
        "os": "windows",
        "depth": max(10, min(20, int(max_results))),
    }
    if settings.DATAFORSEO_LOCATION_CODE:
        payload["location_code"] = settings.DATAFORSEO_LOCATION_CODE
    else:
        payload["location_name"] = settings.DATAFORSEO_DEFAULT_LOCATION
    if settings.DATAFORSEO_LANGUAGE_CODE:
        payload["language_code"] = settings.DATAFORSEO_LANGUAGE_CODE
    else:
        payload["language_name"] = settings.DATAFORSEO_DEFAULT_LANGUAGE

    try:
        response, cost, cached = _request(
            db, "serp/google/organic/live/regular", payload,
        )
    except Exception as exc:
        logger.warning("DataForSEO competitor SERP failed for %r: %s", keyword, exc)
        return []

    results: list[dict[str, Any]] = []
    for task in response.get("tasks") or []:
        for result in task.get("result") or []:
            for item in result.get("items") or []:
                if item.get("type") not in {"organic", "featured_snippet"}:
                    continue
                url = item.get("url")
                if not isinstance(url, str) or not url.startswith(("http://", "https://")):
                    continue
                results.append({
                    "url": url,
                    "title": item.get("title"),
                    "snippet": item.get("description"),
                })
                if len(results) >= max_results:
                    break
            if len(results) >= max_results:
                break
        if len(results) >= max_results:
            break
    logger.info(
        "DataForSEO competitor SERP returned %s results for %r (%s, $%.4f)",
        len(results), keyword, "cache" if cached else "paid", cost,
    )
    return results
