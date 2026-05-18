import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.config import APP_BASE_URL, COOKIE_SECURE
from core.database import get_db
from core.security import (
    get_current_user, hash_password, verify_password,
    create_access_token, create_pending_2fa_token, verify_pending_2fa_token,
)
from models.enums import UserRole
from models.user import User, Wallet, PasswordResetToken
from models.support import RoleConfig, EmailVerificationToken
from services.email import send_reset_email, send_verification_email
from services.notifications import log_activity
from services.rate_limiter import check_rate_limit
from services.settings import get_setting
from routers.deps import render

router = APIRouter(tags=["auth"])


async def _rl_on(db: AsyncSession) -> bool:
    return (await get_setting(db, "rate_limiting")) == "1"


async def _visible_roles(db: AsyncSession) -> list[dict]:
    configs = (await db.execute(
        select(RoleConfig).where(RoleConfig.visible_at_registration == True)
    )).scalars().all()
    return [{"value": rc.role_name, "label": rc.label} for rc in configs
            if rc.role_name in ("buyer", "author")]


# ── Login ──────────────────────────────────────────────────────────────────────

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    if user:
        return RedirectResponse("/profile", 302)
    return render(request, "auth/login.html", {"user": None, "error": None})


@router.post("/login")
async def login_post(request: Request, db: AsyncSession = Depends(get_db),
                     email: str = Form(...), password: str = Form(...)):
    client_ip = request.client.host if request.client else "unknown"
    await check_rate_limit(f"login:{client_ip}", 5, 60, await _rl_on(db))

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.hashed_password):
        return render(request, "auth/login.html", {"user": None, "error": "Неверный email или пароль"})
    if user.is_banned:
        return render(request, "auth/login.html",
                      {"user": None, "error": f"Аккаунт заблокирован: {user.ban_reason}"})

    # 2FA check
    if user.totp_enabled and user.totp_secret:
        pending_token = create_pending_2fa_token(user.id)
        response = RedirectResponse("/auth/2fa-verify", status_code=302)
        response.set_cookie("_2fa_pending", pending_token, httponly=True,
                            max_age=600, samesite="lax", secure=COOKIE_SECURE)
        return response

    token = create_access_token({"sub": str(user.id)})
    await log_activity(db, user.id, "login", "user", user.id,
                       ip=request.client.host if request.client else "")
    await db.commit()
    response = RedirectResponse("/profile", status_code=302)
    response.set_cookie("access_token", token, httponly=True,
                        max_age=60 * 60 * 24 * 30, samesite="lax", secure=COOKIE_SECURE)
    return response


# ── Register ───────────────────────────────────────────────────────────────────

@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    if user:
        return RedirectResponse("/profile", 302)
    roles = await _visible_roles(db)
    return render(request, "auth/register.html", {"user": None, "error": None, "roles": roles})


@router.post("/register")
async def register_post(request: Request, db: AsyncSession = Depends(get_db),
                        email: str = Form(...), username: str = Form(...),
                        password: str = Form(...), full_name: str = Form(""),
                        role: str = Form("buyer"), email_consent: str = Form("0")):
    client_ip = request.client.host if request.client else "unknown"
    await check_rate_limit(f"register:{client_ip}", 3, 60, await _rl_on(db))

    roles = await _visible_roles(db)
    ctx = {"user": None, "roles": roles}

    if len(password) < 8:
        return render(request, "auth/register.html",
                      {**ctx, "error": "Пароль должен быть не менее 8 символов"})
    existing = (await db.execute(
        select(User).where(or_(User.email == email, User.username == username))
    )).scalar_one_or_none()
    if existing:
        return render(request, "auth/register.html",
                      {**ctx, "error": "Email или username уже занят"})

    allowed = {r["value"] for r in roles}
    if role not in allowed:
        role = "buyer"

    new_user = User(
        email=email, username=username, hashed_password=hash_password(password),
        role=UserRole(role), full_name=full_name, is_active=True,
        email_consent=(email_consent == "1"),
        email_verified=False,
    )
    db.add(new_user)
    await db.flush()
    db.add(Wallet(user_id=new_user.id))
    await log_activity(db, new_user.id, "register", "user", new_user.id)

    # Email verification token
    verify_token = secrets.token_urlsafe(48)
    db.add(EmailVerificationToken(
        user_id=new_user.id,
        token=verify_token,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    ))
    await db.commit()
    send_verification_email(new_user.email, verify_token, APP_BASE_URL)

    token = create_access_token({"sub": str(new_user.id)})
    response = RedirectResponse("/profile", status_code=302)
    response.set_cookie("access_token", token, httponly=True,
                        max_age=60 * 60 * 24 * 30, samesite="lax", secure=COOKIE_SECURE)
    return response


# ── Email verification ─────────────────────────────────────────────────────────

@router.get("/verify-email/{token}", response_class=HTMLResponse)
async def verify_email(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    vt = (await db.execute(
        select(EmailVerificationToken)
        .options(selectinload(EmailVerificationToken.user))
        .where(EmailVerificationToken.token == token,
               EmailVerificationToken.expires_at > datetime.now(timezone.utc))
    )).scalar_one_or_none()
    if not vt:
        return render(request, "auth/verify_email_result.html",
                      {"user": None, "success": False})
    vt.user.email_verified = True
    await db.delete(vt)
    await db.commit()
    return render(request, "auth/verify_email_result.html",
                  {"user": vt.user, "success": True})


@router.post("/resend-verification")
async def resend_verification(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    if not user or user.email_verified:
        return RedirectResponse("/profile", 302)

    # Delete old tokens
    old = (await db.execute(
        select(EmailVerificationToken).where(EmailVerificationToken.user_id == user.id)
    )).scalars().all()
    for t in old:
        await db.delete(t)

    verify_token = secrets.token_urlsafe(48)
    db.add(EmailVerificationToken(
        user_id=user.id,
        token=verify_token,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    ))
    await db.commit()
    send_verification_email(user.email, verify_token, APP_BASE_URL)
    return RedirectResponse("/profile?verification_sent=1", 302)


# ── 2FA Verify ────────────────────────────────────────────────────────────────

@router.get("/auth/2fa-verify", response_class=HTMLResponse)
async def twofa_verify_page(request: Request):
    pending = request.cookies.get("_2fa_pending")
    if not pending or verify_pending_2fa_token(pending) is None:
        return RedirectResponse("/login", 302)
    return render(request, "auth/2fa.html", {"user": None, "error": None})


@router.post("/auth/2fa-verify")
async def twofa_verify_post(request: Request, db: AsyncSession = Depends(get_db),
                            code: str = Form(...)):
    pending = request.cookies.get("_2fa_pending")
    user_id = verify_pending_2fa_token(pending or "")
    if user_id is None:
        return RedirectResponse("/login", 302)

    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user or not user.totp_secret:
        return RedirectResponse("/login", 302)

    import pyotp
    totp = pyotp.TOTP(user.totp_secret)
    if not totp.verify(code.strip(), valid_window=1):
        return render(request, "auth/2fa.html",
                      {"user": None, "error": "Неверный код. Проверьте время в приложении."})

    token = create_access_token({"sub": str(user.id)})
    await log_activity(db, user.id, "login_2fa", "user", user.id,
                       ip=request.client.host if request.client else "")
    await db.commit()
    response = RedirectResponse("/profile", status_code=302)
    response.set_cookie("access_token", token, httponly=True,
                        max_age=60 * 60 * 24 * 30, samesite="lax", secure=COOKIE_SECURE)
    response.delete_cookie("_2fa_pending")
    return response


# ── Logout ────────────────────────────────────────────────────────────────────

@router.get("/logout")
async def logout():
    response = RedirectResponse("/", 302)
    response.delete_cookie("access_token")
    return response


# ── Forgot / Reset password ───────────────────────────────────────────────────

@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    return render(request, "auth/forgot_password.html", {"user": user, "sent": False, "error": None})


@router.post("/forgot-password")
async def forgot_password_post(request: Request, db: AsyncSession = Depends(get_db),
                                email: str = Form(...)):
    client_ip = request.client.host if request.client else "unknown"
    await check_rate_limit(f"forgot:{client_ip}", 3, 300, await _rl_on(db))

    user = await get_current_user(request, db)
    target = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if not target:
        return render(request, "auth/forgot_password.html",
                      {"user": user, "sent": True, "error": None})
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
    send_reset_email(email, token, APP_BASE_URL)
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
