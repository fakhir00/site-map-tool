from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case, desc
from app.config import settings
from app.database import get_db
from app.models import User
from app.schemas import (
    AdminLogin,
    AdminTokenResponse,
    AdminUserRequestOut,
    AdminRejectBody,
)
from app.auth.jwt import create_admin_token, get_current_superadmin, security

router = APIRouter(prefix="/api/admin", tags=["admin"])

UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads" / "payment_proofs"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

SUPERADMIN_ID = "crawladmin@1"
SUPERADMIN_PASSWORD = "crawlgap@7861"


@router.post("/login", response_model=AdminTokenResponse)
async def admin_login(body: AdminLogin):
    if body.admin_id.strip() != SUPERADMIN_ID or body.password != SUPERADMIN_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid superadmin credentials",
        )

    token = create_admin_token(SUPERADMIN_ID)
    return AdminTokenResponse(
        access_token=token,
        token_type="bearer",
        role="superadmin",
        admin_id=SUPERADMIN_ID,
    )


@router.get("/requests", response_model=List[AdminUserRequestOut])
async def list_registration_requests(
    admin_id: str = Depends(get_current_superadmin),
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
):
    query = select(User)

    if status_filter:
        query = query.where(User.status == status_filter)

    # Order priority: pending_approval first, then by created_at descending
    priority = case(
        (User.status == "pending_approval", 1),
        (User.status == "pending_proof", 2),
        (User.status == "rejected", 3),
        else_=4,
    )
    query = query.order_by(priority, desc(User.created_at))

    result = await db.execute(query)
    users = result.scalars().all()

    requests_out = []
    for u in users:
        proof_url = f"/api/admin/proof-image/{u.id}" if u.payment_proof_path else None
        requests_out.append(
            AdminUserRequestOut(
                id=u.id,
                email=u.email,
                full_name=u.full_name,
                status=u.status or ("approved" if u.is_active else "pending_proof"),
                is_active=bool(u.is_active),
                has_payment_proof=bool(u.payment_proof_path),
                payment_proof_filename=u.payment_proof_filename,
                payment_proof_url=proof_url,
                payment_proof_uploaded_at=u.payment_proof_uploaded_at,
                rejection_reason=u.rejection_reason,
                created_at=u.created_at,
                reviewed_at=u.reviewed_at,
            )
        )
    return requests_out


@router.get("/stats")
async def get_admin_stats(
    admin_id: str = Depends(get_current_superadmin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User))
    users = result.scalars().all()

    total = len(users)
    pending_approval = sum(1 for u in users if u.status == "pending_approval")
    approved = sum(1 for u in users if u.status == "approved" or (u.is_active and u.status != "rejected"))
    rejected = sum(1 for u in users if u.status == "rejected")
    pending_proof = sum(1 for u in users if u.status == "pending_proof")

    return {
        "total": total,
        "pending_approval": pending_approval,
        "approved": approved,
        "rejected": rejected,
        "pending_proof": pending_proof,
    }


def _verify_admin_token_string(token: str) -> bool:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload.get("role") == "superadmin" and payload.get("sub") == SUPERADMIN_ID
    except (JWTError, ValueError):
        return False


@router.get("/proof-image/{user_id}")
async def get_proof_image(
    user_id: uuid.UUID,
    token: Optional[str] = Query(None),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
):
    # Support token in query parameter for <img> tags and full screen previews
    is_valid = False
    if credentials and credentials.credentials:
        is_valid = _verify_admin_token_string(credentials.credentials)
    if not is_valid and token:
        is_valid = _verify_admin_token_string(token)

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Superadmin authentication required to view payment proof",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.payment_proof_path:
        raise HTTPException(status_code=404, detail="Payment proof not found for this user")

    file_path = UPLOAD_DIR / user.payment_proof_path
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Proof file missing on storage")

    return FileResponse(file_path, filename=user.payment_proof_filename or "proof.png")


@router.post("/requests/{user_id}/approve")
async def approve_user_request(
    user_id: uuid.UUID,
    admin_id: str = Depends(get_current_superadmin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = True
    user.status = "approved"
    user.rejection_reason = None
    user.reviewed_at = datetime.now(timezone.utc)
    await db.flush()

    return {
        "success": True,
        "message": f"Account for {user.email} has been approved and activated.",
        "user_id": str(user.id),
        "status": "approved",
    }


@router.post("/requests/{user_id}/reject")
async def reject_user_request(
    user_id: uuid.UUID,
    body: AdminRejectBody,
    admin_id: str = Depends(get_current_superadmin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    default_reason = "Payment proof could not be verified. Please verify your information and try again or contact customer support."
    reason = (body.reason or "").strip() or default_reason

    user.is_active = False
    user.status = "rejected"
    user.rejection_reason = reason
    user.reviewed_at = datetime.now(timezone.utc)
    await db.flush()

    return {
        "success": True,
        "message": f"Registration for {user.email} has been rejected.",
        "user_id": str(user.id),
        "status": "rejected",
        "rejection_reason": reason,
    }
