import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.jwt import get_current_user
from app.models import User
from nlp.keywords import clean_phrase, is_valid_keyword
from nlp.openrouter import _achat_json, cluster_hub_and_spoke, is_ai_configured

router = APIRouter(prefix="/api/hub-spoke", tags=["hub-spoke-workspace"])


class KeywordWorkspaceRequest(BaseModel):
    keywords: list[str] = Field(min_length=1, max_length=5000)
    context: str = Field(default="", max_length=12000)


def _basic_clean(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        for raw in str(value).replace("\r", "\n").split("\n"):
            # CSV rows commonly contain a keyword in the first column.
            phrase = clean_phrase(raw.split(",", 1)[0].strip().strip('"'))
            if not is_valid_keyword(phrase, min_words=1) or phrase in result:
                continue
            result.append(phrase)
    return result


async def _clean_with_context(keywords: list[str], context: str) -> list[str]:
    cleaned = _basic_clean(keywords)
    if not cleaned or not is_ai_configured():
        return cleaned

    accepted: list[str] = []
    for start in range(0, len(cleaned), 200):
        chunk = cleaned[start:start + 200]
        prompt = f"""
You are a strict SEO keyword-list cleaner.

Website/product context:
{context or "No extra context. Infer the dominant topic shared by the keyword list."}

Candidate keywords:
{json.dumps(chunk)}

Return only useful keywords that fit the context's subject, audience, product capabilities,
boundaries, and search intent. Remove navigation text, broken phrases, unrelated topics,
brand drift, obvious extraction junk, and exact duplicates. Keep useful questions, use cases,
comparisons, entities, and supporting phrases even when they may later become H2 sections.
You may only return exact strings from Candidate keywords. Order the strongest primary topic first.
Return JSON: {{"keywords": ["exact candidate", "exact candidate"]}}
"""
        try:
            payload = await _achat_json(
                system_prompt="Return only valid JSON and never invent a keyword.",
                user_prompt=prompt,
                temperature=0.1,
                max_tokens=3500,
            )
        except Exception:
            payload = None
        selected = payload.get("keywords") if isinstance(payload, dict) else None
        if not isinstance(selected, list):
            accepted.extend(chunk)
            continue
        allowed = set(chunk)
        for item in selected:
            phrase = clean_phrase(str(item))
            if phrase in allowed:
                accepted.append(phrase)
    return list(dict.fromkeys(accepted))


@router.post("/clean")
async def clean_uploaded_keywords(
    body: KeywordWorkspaceRequest,
    _current_user: User = Depends(get_current_user),
):
    keywords = await _clean_with_context(body.keywords, body.context)
    if not keywords:
        raise HTTPException(status_code=422, detail="No relevant keywords remained after cleaning.")
    return {"keywords": keywords, "count": len(keywords)}


@router.post("/build")
async def build_uploaded_hub_spoke(
    body: KeywordWorkspaceRequest,
    _current_user: User = Depends(get_current_user),
):
    keywords = await _clean_with_context(body.keywords, body.context)
    if not keywords:
        raise HTTPException(status_code=422, detail="Upload a keyword list with at least one usable keyword.")
    typed = [{"phrase": phrase, "type": "long-tail"} for phrase in keywords]
    mapping = await cluster_hub_and_spoke(
        typed,
        main_keyword=keywords[0],
        audit_summary=body.context or "Uploaded keyword research list",
    )
    if not mapping:
        raise HTTPException(status_code=502, detail="Could not build a constraint-safe hub-spoke map from this list.")
    return {"keywords": keywords, "count": len(keywords), "clusters": mapping}
