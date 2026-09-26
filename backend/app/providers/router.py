from fastapi import APIRouter, Depends

from app.auth.jwt import get_current_user
from app.models import User
from nlp.dataforseo import dataforseo_account_status
from scraping.apify_client_module import apify_account_status


router = APIRouter(prefix="/api/providers", tags=["providers"])


@router.get("/dataforseo/status")
def dataforseo_status(_current_user: User = Depends(get_current_user)) -> dict:
    return dataforseo_account_status()


@router.get("/apify/status")
def apify_status(_current_user: User = Depends(get_current_user)) -> dict:
    return apify_account_status()


@router.get("/ai/status")
def ai_status(_current_user: User = Depends(get_current_user)) -> dict:
    from nlp.providers import provider_status
    return provider_status()


@router.post("/ai/check")
def ai_check(_current_user: User = Depends(get_current_user)) -> dict:
    from nlp.providers import check_providers
    return check_providers()
