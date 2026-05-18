from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import JWTError, ExpiredSignatureError, jwt
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_DAYS

_2FA_KEY_SUFFIX = "_2fa_pending"


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_pending_2fa_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=10)
    payload = {"sub": str(user_id), "pending_2fa": True, "exp": expire}
    return jwt.encode(payload, SECRET_KEY + _2FA_KEY_SUFFIX, algorithm=ALGORITHM)


def verify_pending_2fa_token(token: str) -> Optional[int]:
    try:
        payload = jwt.decode(token, SECRET_KEY + _2FA_KEY_SUFFIX, algorithms=[ALGORITHM])
        if not payload.get("pending_2fa"):
            return None
        return int(payload["sub"])
    except Exception:
        return None


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
    except ExpiredSignatureError:
        request.state.token_expired = True
        return None
    except JWTError:
        return None
    result = await db.execute(select(User).where(User.id == int(user_id)))
    u = result.scalar_one_or_none()
    if u is None or u.is_banned:
        return None
    u.last_seen = datetime.now(timezone.utc)
    await db.commit()
    return u
