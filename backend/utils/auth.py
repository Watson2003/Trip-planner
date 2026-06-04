from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import async_session_maker
from models.trip import User
from models.user_schemas import TokenData, UserResponse
from utils.config import settings


ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _get_secret_key() -> str:
    if not settings.secret_key:
        raise RuntimeError("SECRET_KEY is not configured in backend/.env")
    return settings.secret_key


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    payload = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    payload.update({"exp": expire})
    return jwt.encode(payload, _get_secret_key(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> TokenData | None:
    try:
        payload = jwt.decode(token, _get_secret_key(), algorithms=[ALGORITHM])
    except JWTError:
        return None

    email = payload.get("email") or payload.get("sub")
    user_id = payload.get("user_id")
    if user_id is not None:
        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            return None

    if email is not None:
        email = str(email)

    return TokenData(email=email, user_id=user_id)


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


def _legacy_identifier_from_username(identifier: str) -> tuple[str, str]:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", identifier.strip().lower())
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    base = cleaned or "guest"
    return base, f"{base}@local"


async def get_or_create_user_from_identifier(session: AsyncSession, identifier: str) -> User:
    username, email = _legacy_identifier_from_username(identifier)

    existing = await session.execute(select(User).where((User.username == username) | (User.email == email)))
    user = existing.scalar_one_or_none()
    if user is not None:
        return user

    user = User(
        username=username,
        email=email,
        hashed_password=hash_password(f"legacy-{username}"),
        full_name=None,
        is_active=True,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def get_current_user(token: str = Depends(oauth2_scheme)) -> UserResponse:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token_data = decode_access_token(token)
    if token_data is None:
        raise credentials_exception

    async with async_session_maker() as session:
        user: User | None = None
        if token_data.user_id is not None:
            user = await get_user_by_id(session, token_data.user_id)
        if user is None and token_data.email is not None:
            user = await get_user_by_email(session, str(token_data.email))

        if user is None or not user.is_active:
            raise credentials_exception

        return UserResponse.model_validate(user)
