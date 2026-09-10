from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
import uuid
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from app.database import get_db
from app.auth.jwt import get_current_user
from app.models import User, GoldHunterScan
from app.goldhunter.scraper import fetch_url_content
from nlp.openrouter import generate_gold_hunter_seeds
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/goldhunter", tags=["goldhunter"])

class ScanRequest(BaseModel):
    url: str

class SeedModel(BaseModel):
    keyword: str
    justification: str

class ScanResponse(BaseModel):
    id: uuid.UUID
    input_url: str
    audit_summary: Optional[str]
    seeds: Optional[List[SeedModel]]
    created_at: datetime

@router.post("/scan", response_model=ScanResponse)
async def scan_gold_hunter(
    req: ScanRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not req.url:
        raise HTTPException(status_code=400, detail="URL is required")
        
    # 1. Ensure URL has a scheme
    target_url = req.url
    if not target_url.startswith(("http://", "https://")):
        target_url = f"https://{target_url}"
        
    # 2. Fetch URL visible content
    url_content = await fetch_url_content(target_url)
    if not url_content:
        raise HTTPException(status_code=400, detail="Failed to fetch or extract content from the provided URL. Ensure it's a valid website.")
        
    # 2. Call the AI Agent
    result = await generate_gold_hunter_seeds(target_url, url_content)
    if not result:
        raise HTTPException(status_code=500, detail="AI generation failed.")
        
    audit_data = result.get("audit_summary", "")
    if isinstance(audit_data, dict):
        audit_data = dict(audit_data)
        audit_data.pop("competitor_profile", None)
    audit_summary = audit_data
    if isinstance(audit_summary, dict):
        import json
        audit_summary = json.dumps(audit_summary, indent=2)

    from nlp.keywords import (
        is_topic_relevant_keyword, normalize_seed_keywords, seed_keyword_terms,
        site_scope_terms,
    )
    normalized_seeds = []
    for item in result.get("seeds", []) or []:
        if not isinstance(item, dict):
            continue
        for keyword in normalize_seed_keywords([item.get("keyword", "")]):
            if any(seed["keyword"] == keyword for seed in normalized_seeds):
                continue
            normalized_seeds.append({
                "keyword": keyword,
                "justification": str(item.get("justification") or "Selected from the Gold Hunter audit."),
            })

    audit_primary = ""
    if isinstance(audit_data, dict):
        primary_values = normalize_seed_keywords([str(audit_data.get("primary_keyword") or "")])
        audit_primary = primary_values[0] if primary_values else ""
    if audit_primary:
        primary_terms = seed_keyword_terms([audit_primary]) | {
            f"__scope__{term}" for term in site_scope_terms(
                audit_primary,
                audit_data if isinstance(audit_data, dict) else None,
            )
        }
        normalized_seeds = [
            seed for seed in normalized_seeds
            if is_topic_relevant_keyword(seed["keyword"], [audit_primary], primary_terms)
        ]

    # The gap scan needs multiple discovery angles. If a provider truncates its
    # JSON, complete the set from the audited primary topic and opportunities.
    if len(normalized_seeds) < 3 and isinstance(audit_data, dict):
        primary_keyword = audit_primary
        audit_candidates = [
            primary_keyword,
            *(audit_data.get("content_opportunities") or []),
            *([f"{primary_keyword} guide", f"best {primary_keyword}"] if primary_keyword else []),
        ]
        for candidate in audit_candidates:
            values = normalize_seed_keywords([str(candidate)])
            if not values:
                continue
            keyword = values[0]
            if primary_keyword and not is_topic_relevant_keyword(
                keyword, [primary_keyword], seed_keyword_terms([primary_keyword])
            ):
                keyword = f"{primary_keyword} {keyword}"
            if any(seed["keyword"] == keyword for seed in normalized_seeds):
                continue
            normalized_seeds.append({
                "keyword": keyword,
                "justification": "Derived from the audited primary topic and content opportunities to provide a distinct, relevant gap-discovery angle.",
            })
            if len(normalized_seeds) >= 3:
                break
    normalized_seeds = normalized_seeds[:5]
    if len(normalized_seeds) < 3:
        raise HTTPException(status_code=502, detail="Gold Hunter could not produce the required 3 relevant seed keywords. Please retry the audit.")

    # 3. Save to database
    scan = GoldHunterScan(
        user_id=current_user.id,
        input_url=target_url,
        audit_summary=audit_summary,
        seeds=normalized_seeds
    )
    db.add(scan)
    await db.commit()
    await db.refresh(scan)
    
    return scan

@router.get("/history", response_model=List[ScanResponse])
async def get_scan_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    query = select(GoldHunterScan).where(GoldHunterScan.user_id == current_user.id).order_by(desc(GoldHunterScan.created_at))
    result = await db.execute(query)
    scans = result.scalars().all()
    return scans
