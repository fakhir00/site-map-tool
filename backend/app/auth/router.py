from datetime import datetime, timezone
import os
from pathlib import Path
import re
import uuid
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models import User
from app.schemas import (
    UserRegister,
    UserLogin,
    TokenResponse,
    UserOut,
    RegisterResponse,
    PaymentProofResponse,
    RegistrationStatusResponse,
)
from app.auth.jwt import hash_password, verify_password, create_access_token, get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])

UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads" / "payment_proofs"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _clean_filename(filename: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]", "_", filename or "proof")
    return cleaned[:100]


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(body: UserRegister, db: AsyncSession = Depends(get_db)):
    email = body.email.lower().strip()
    result = await db.execute(select(User).where(User.email == email))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        if existing_user.status == "approved" or (existing_user.is_active and existing_user.status != "rejected"):
            raise HTTPException(status_code=400, detail="Email already registered")
        if existing_user.status == "pending_approval":
            raise HTTPException(status_code=400, detail="An account with this email is already awaiting approval")

        # Allow updating credentials if previously pending proof or rejected
        existing_user.password_hash = hash_password(body.password)
        if body.full_name:
            existing_user.full_name = body.full_name.strip()
        existing_user.status = "pending_proof"
        existing_user.is_active = False
        existing_user.rejection_reason = None
        await db.flush()
        return RegisterResponse(
            message="Account details saved. Please upload your payment proof to complete registration.",
            status="pending_proof",
            email=existing_user.email,
            full_name=existing_user.full_name,
        )

    user = User(
        email=email,
        password_hash=hash_password(body.password),
        full_name=body.full_name.strip() if body.full_name else None,
        is_active=False,
        status="pending_proof",
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    return RegisterResponse(
        message="Account created. Please upload your payment proof to complete registration.",
        status="pending_proof",
        email=user.email,
        full_name=user.full_name,
    )


@router.post("/upload-payment-proof", response_model=PaymentProofResponse)
async def upload_payment_proof(
    email: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    clean_email = email.lower().strip()
    result = await db.execute(select(User).where(User.email == clean_email))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User account not found for this email")

    if not file.filename:
        raise HTTPException(status_code=400, detail="Uploaded file must have a valid filename")

    # Accept any image format (png, jpg, jpeg, webp, gif, svg, bmp, heic, tiff, etc.)
    ext = os.path.splitext(file.filename)[1].lower()
    valid_extensions = {
        ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg",
        ".heic", ".heif", ".tiff", ".tif", ".avif", ".jfif", ".ico", ".pdf"
    }
    content_type = file.content_type or ""

    if ext not in valid_extensions and not content_type.startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail="Payment proof must be an image (PNG, JPG, WebP, GIF, SVG, HEIC, etc.)",
        )

    safe_name = _clean_filename(file.filename)
    unique_filename = f"{uuid.uuid4().hex}_{safe_name}"
    target_path = UPLOAD_DIR / unique_filename

    # Read and save file content
    contents = await file.read()
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="The uploaded file is empty")

    with open(target_path, "wb") as f:
        f.write(contents)

    user.payment_proof_path = unique_filename
    user.payment_proof_filename = file.filename
    user.payment_proof_uploaded_at = datetime.now(timezone.utc)
    user.status = "pending_approval"
    user.rejection_reason = None
    await db.flush()

    return PaymentProofResponse(
        message="Payment proof uploaded successfully. Your account is on the waitlist awaiting approval.",
        status="pending_approval",
        email=user.email,
    )


@router.get("/registration-status", response_model=RegistrationStatusResponse)
async def registration_status(email: str, db: AsyncSession = Depends(get_db)):
    clean_email = email.lower().strip()
    result = await db.execute(select(User).where(User.email == clean_email))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="No registration found for this email")

    return RegistrationStatusResponse(
        email=user.email,
        full_name=user.full_name,
        status=user.status or "pending_proof",
        is_active=bool(user.is_active),
        has_proof=bool(user.payment_proof_path),
        uploaded_at=user.payment_proof_uploaded_at,
        rejection_reason=user.rejection_reason,
    )


@router.get("/proof-preview")
async def preview_proof(email: str, db: AsyncSession = Depends(get_db)):
    clean_email = email.lower().strip()
    result = await db.execute(select(User).where(User.email == clean_email))
    user = result.scalar_one_or_none()

    if not user or not user.payment_proof_path:
        raise HTTPException(status_code=404, detail="Proof not found")

    file_path = UPLOAD_DIR / user.payment_proof_path
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Proof file not found on server")

    return FileResponse(file_path, filename=user.payment_proof_filename or "payment-proof.png")


@router.post("/login", response_model=TokenResponse)
async def login(body: UserLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email.lower().strip()))
    user = result.scalar_one_or_none()

    if not user or not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Check approval status
    user_status = user.status or ("approved" if user.is_active else "pending_proof")

    if user_status == "pending_proof":
        raise HTTPException(
            status_code=403,
            detail={
                "code": "PENDING_PROOF",
                "status": "pending_proof",
                "email": user.email,
                "message": "Please upload your payment proof to continue.",
            },
        )

    if user_status == "pending_approval":
        raise HTTPException(
            status_code=403,
            detail={
                "code": "PENDING_APPROVAL",
                "status": "pending_approval",
                "email": user.email,
                "message": "Your payment proof is currently under review. Please wait for approval.",
            },
        )

    if user_status == "rejected":
        raise HTTPException(
            status_code=403,
            detail={
                "code": "REJECTED",
                "status": "rejected",
                "email": user.email,
                "rejection_reason": user.rejection_reason,
                "message": user.rejection_reason or "Your payment proof was not approved. Please verify your information and try again or contact customer support.",
            },
        )

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled. Contact customer support.")

    token = create_access_token(user.id)
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    return UserOut.model_validate(current_user)
