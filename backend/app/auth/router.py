from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models import User
from app.schemas import UserRegister, UserLogin, TokenResponse, UserOut
from app.auth.jwt import hash_password, verify_password, create_access_token, get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: UserRegister, db: AsyncSession = Depends(get_db)):
    email = body.email.lower()
    result = await db.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=email,
        password_hash=hash_password(body.password),
        full_name=body.full_name.strip() if body.full_name else None,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    token = create_access_token(user.id)
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenResponse)
async def login(body: UserLogin, db: AsyncSession = Depends(get_db)):
    import logging
    logger = logging.getLogger(__name__)
    logger.error(f"DEBUG: Login attempt for email '{body.email}' password '{body.password}'")
    with open('/Users/fakhirbaig/Documents/GitHub/sit map tool/backend/login_debug.txt', 'a') as f:
        f.write(f"Login attempt: email='{body.email}', password='{body.password}'\n")
        
    result = await db.execute(select(User).where(User.email == body.email.lower()))
    user = result.scalar_one_or_none()

    if not user:
        with open('/Users/fakhirbaig/Documents/GitHub/sit map tool/backend/login_debug.txt', 'a') as f:
            f.write("Failed: user not found\n")
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    if not user.password_hash:
        with open('/Users/fakhirbaig/Documents/GitHub/sit map tool/backend/login_debug.txt', 'a') as f:
            f.write("Failed: no password hash\n")
        raise HTTPException(status_code=401, detail="Invalid email or password")
        
    if not verify_password(body.password, user.password_hash):
        with open('/Users/fakhirbaig/Documents/GitHub/sit map tool/backend/login_debug.txt', 'a') as f:
            f.write("Failed: verify_password returned False\n")
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.is_active:
        with open('/Users/fakhirbaig/Documents/GitHub/sit map tool/backend/login_debug.txt', 'a') as f:
            f.write("Failed: not active\n")
        raise HTTPException(status_code=403, detail="Account disabled")

    with open('/Users/fakhirbaig/Documents/GitHub/sit map tool/backend/login_debug.txt', 'a') as f:
        f.write("Success!\n")
    token = create_access_token(user.id)
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    return UserOut.model_validate(current_user)
