from fastapi import APIRouter, Depends, HTTPException
from starlette.concurrency import run_in_threadpool
import logging

from app.auth.jwt import get_current_user
from app.models import User
from app.schemas import (
    WebsiteIntentRequest,
    WebsiteIntentResponse,
    WebsitePromptGenerateRequest,
    WebsitePromptGenerateResponse
)
from app.website_prompts.service import analyze_intent_flow, generate_prompt_flow, generate_gap_page_flow

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/website-prompts", tags=["website_prompts"])

@router.post("/analyze-intent", response_model=WebsiteIntentResponse)
async def analyze_intent(
    req: WebsiteIntentRequest,
    current_user: User = Depends(get_current_user),
):
    try:
        result = await run_in_threadpool(
            analyze_intent_flow,
            keyword=req.keyword,
            manual_competitors=req.manual_competitors,
            short_mode=req.short_mode
        )
        return WebsiteIntentResponse(
            intent=result["intent"],
            competitors=result["competitors"]
        )
    except Exception as e:
        logger.error(f"Error in analyze_intent: {e}")
        raise HTTPException(status_code=500, detail="Failed to analyze intent")


@router.post("/generate", response_model=WebsitePromptGenerateResponse)
async def generate_prompt(
    req: WebsitePromptGenerateRequest,
    current_user: User = Depends(get_current_user),
):
    try:
        result = await run_in_threadpool(
            generate_prompt_flow,
            keyword=req.keyword,
            intent=req.intent,
            competitors=req.competitors
        )
        return WebsitePromptGenerateResponse(
            prompt=result["prompt"],
            attempts=result["attempts"],
            audit_score=result["audit_score"]
        )
    except Exception as e:
        logger.error(f"Error in generate_prompt: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate website prompt")


@router.post("/generate-gap-page", response_model=WebsitePromptGenerateResponse)
async def generate_gap_page(
    req: WebsitePromptGenerateRequest,
    current_user: User = Depends(get_current_user),
):
    try:
        result = await run_in_threadpool(
            generate_gap_page_flow,
            keyword=req.keyword,
            intent=req.intent,
            competitors=req.competitors
        )
        return WebsitePromptGenerateResponse(
            prompt=result["prompt"],
            attempts=result["attempts"],
            audit_score=result["audit_score"]
        )
    except Exception as e:
        logger.error(f"Error in generate_gap_page: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate gap page prompt")

