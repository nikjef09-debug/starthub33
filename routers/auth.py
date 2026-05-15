import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.database import get_db
from core.security import get_current_user, hash_password, verify_password, create_access_token
from models.enums import UserRole
from models.user import User, Wallet, PasswordResetToken
from services.email import send_reset_email
from services.notifications import log_activity
from routers.deps import render

router = APIRouter(tags=["auth"])


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    if user:
        return RedirectResponse("/profile", 302)
    return render(request, "auth/login.html", {"user": None, "error": None})


@router.post("/login")
async def login_post(request: Request, db: AsyncSession = Depends(get_db),
                     email: str = Form(...), password: str = Form(...)):
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.hashed_password):
        return render(request, "auth/login.html", {"user": None, "error": "Неверный email или пароль"})
    if user.is_banned:
        return render(request, "auth/login.html",
                      {"user": None, "error": f"Аккаунт заблокирован: {user.ban_reason}"})
    token = create_access_token({"sub": str(user.id)})
    await log_activity(db, user.id, "login", "user", user.id,
                       ip=request.client.host if request.client else "")
    await db.commit()
    response = RedirectResponse("/profile", status_code=302)
    response.set_cookie("access_token", token, httponly=True,
                        max_age=60 * 60 * 24 * 30, samesite="lax")
    return response


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    if user:
        return RedirectResponse("/profile", 302)
    return render(request, "auth/register.html", {"user": None, "error": None})


@router.post("/register")
async def register_post(request: Request, db: AsyncSession = Depends(get_db),
                        email: str = Form(...), username: str = Form(...),
                        password: str = Form(...), full_name: str = Form(""),
                        role: str = Form("buyer")):
    if len(password) < 8:
        return render(request, "auth/register.html",
                      {"user": None, "error": "Пароль должен быть не менее 8 символов"})
    existing = (await db.execute(
        select(User).where(or_(User.email == email, User.username == username))
    )).scalar_one_or_none()
    if existing:
        return render(request, "auth/register.html",
                      {"user": None, "error": "Email или username уже занят"})
    if role not in ("author", "buyer"):
        role = "buyer"
    new_user = User(email=email, username=username, hashed_password=hash_password(password),
                    role=UserRole(role), full_name=full_name, is_active=True)
    db.add(new_user)
    await db.flush()
    db.add(Wallet(user_id=new_user.id))
    await log_activity(db, new_user.id, "register", "user", new_user.id)
    await db.commit()
    token = create_access_token({"sub": str(new_user.id)})
    response = RedirectResponse("/profile", status_code=302)
    response.set_cookie("access_token", token, httponly=True,
                        max_age=60 * 60 * 24 * 30, samesite="lax")
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse("/", 302)
    response.delete_cookie("access_token")
    return response


@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    return render(request, "auth/forgot_password.html", {"user": user, "sent": False, "error": None})


@router.post("/forgot-password")
async def forgot_password_post(request: Request, db: AsyncSession = Depends(get_db),
                                email: str = Form(...)):
    user = await get_current_user(request, db)
    target = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if not target:
        return render(request, "auth/forgot_password.html",
                      {"user": user, "sent": True, "error": None})
    # Удаляем старые неиспользованные токены
    old_tokens = (await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.user_id == target.id,
            PasswordResetToken.is_used == False,
        )
    )).scalars().all()
    for t in old_tokens:
        await db.delete(t)
    token = secrets.token_urlsafe(48)
    expires = datetime.now(timezone.utc) + timedelta(hours=2)
    db.add(PasswordResetToken(user_id=target.id, token=token, expires_at=expires))
    await db.commit()
    try:
        await send_reset_email(email, token)
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")
    return render(request, "auth/forgot_password.html",
                  {"user": user, "sent": True, "error": None})


@router.get("/reset-password/{token}", response_class=HTMLResponse)
async def reset_password_page(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    reset = (await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token == token,
            PasswordResetToken.is_used == False,
            PasswordResetToken.expires_at > datetime.now(timezone.utc),
        )
    )).scalar_one_or_none()
    if not reset:
        return render(request, "auth/reset_password.html",
                      {"user": user, "token": token, "error": "Ссылка недействительна или истекла.",
                       "success": False, "invalid": True})
    return render(request, "auth/reset_password.html",
                  {"user": user, "token": token, "error": None, "success": False, "invalid": False})


@router.post("/reset-password/{token}")
async def reset_password_post(token: str, request: Request, db: AsyncSession = Depends(get_db),
                               password: str = Form(...), password2: str = Form(...)):
    user = await get_current_user(request, db)
    base = {"user": user, "token": token, "success": False, "invalid": False}
    if password != password2:
        return render(request, "auth/reset_password.html", {**base, "error": "Пароли не совпадают"})
    if len(password) < 8:
        return render(request, "auth/reset_password.html",
                      {**base, "error": "Пароль должен быть минимум 8 символов"})
    reset = (await db.execute(
        select(PasswordResetToken)
        .options(selectinload(PasswordResetToken.user))
        .where(PasswordResetToken.token == token,
               PasswordResetToken.is_used == False,
               PasswordResetToken.expires_at > datetime.now(timezone.utc))
    )).scalar_one_or_none()
    if not reset:
        return render(request, "auth/reset_password.html",
                      {**base, "error": "Ссылка недействительна или истекла.", "invalid": True})
    reset.user.hashed_password = hash_password(password)
    reset.is_used = True
    await db.commit()
    return render(request, "auth/reset_password.html", {**base, "error": None, "success": True})
