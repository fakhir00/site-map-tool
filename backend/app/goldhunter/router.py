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
from scraping.apify_client_module import search_google_via_apify
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
        
    # 3. Save to database
    scan = GoldHunterScan(
        user_id=current_user.id,
        input_url=target_url,
        audit_summary=result.get("audit_summary", ""),
        seeds=result.get("seeds", [])
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
