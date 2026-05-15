from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_DAYS

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(request: Request, db: AsyncSession) -> Optional["User"]:  # noqa
    from models.user import User
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            return None
    except JWTError:
        return None
    result = await db.execute(select(User).where(User.id == int(user_id)))
    u = result.scalar_one_or_none()
    if u and not u.is_banned:
        u.last_seen = datetime.now(timezone.utc)
        await db.commit()
    return u
