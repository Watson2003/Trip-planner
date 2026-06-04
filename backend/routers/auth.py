from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import async_session_maker
from models.trip import User
from models.user_schemas import Token, UserCreate, UserLogin, UserResponse
from utils.auth import create_access_token, get_current_user, hash_password, verify_password


router = APIRouter(tags=["auth"])


async def get_session() -> AsyncSession:
    async with async_session_maker() as session:
        yield session


def _normalize_email(email: str) -> str:
    return email.strip().lower()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, session: AsyncSession = Depends(get_session)) -> UserResponse:
    username = payload.username.strip()
    email = _normalize_email(payload.email)
    full_name = payload.full_name.strip() if payload.full_name else None

    if not username or not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username and email are required")

    if len(payload.password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password must be at least 8 characters long")

    existing_email = await session.execute(select(User).where(User.email == email))
    if existing_email.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    existing_username = await session.execute(select(User).where(User.username == username))
    if existing_username.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already taken")

    user = User(
        username=username,
        email=email,
        hashed_password=hash_password(payload.password),
        full_name=full_name,
        is_active=True,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return UserResponse.model_validate(user)


@router.post("/login", response_model=Token)
async def login(payload: UserLogin, session: AsyncSession = Depends(get_session)) -> Token:
    email = _normalize_email(payload.email)
    if not email or not payload.password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive")

    if not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    access_token = create_access_token({"sub": user.email, "email": user.email, "user_id": user.id})
    return Token(access_token=access_token, token_type="bearer")


@router.get("/me", response_model=UserResponse)
async def read_me(current_user: UserResponse = Depends(get_current_user)) -> UserResponse:
    return current_user


@router.post("/logout")
async def logout() -> dict[str, str]:
    return {"message": "Logged out successfully"}
