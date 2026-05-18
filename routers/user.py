import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import func, select, update, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.config import MAX_IMAGE_SIZE, AVATAR_SIZE
from core.database import get_db
from core.security import get_current_user
from models.enums import (
    UserRole, StartupStatus, ReviewTarget, TicketPriority, WithdrawStatus,
)
from models.startup import Startup
from models.deal import Deal
from models.support import Notification, Review, SupportTicket
from models.user import User, Wallet, Transaction, ActivityLog
from services.notifications import create_notification, log_activity
from utils.helpers import save_image, slugify
from routers.deps import render
from models.subscription import Subscription

router = APIRouter()





# ── Profile ────────────────────────────────────────────────────────────────────

@router.get("/profile", response_class=HTMLResponse)
async def profile(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", 302)
    wallet = (await db.execute(select(Wallet).where(Wallet.user_id == user.id))).scalar_one_or_none()
    activity = (await db.execute(
        select(ActivityLog).where(ActivityLog.user_id == user.id)
        .order_by(ActivityLog.created_at.desc()).limit(10)
    )).scalars().all()
    unread_notifs = (await db.execute(
        select(func.count(Notification.id))
        .where(Notification.user_id == user.id, Notification.is_read == False)
    )).scalar()
    if user.role == UserRole.author:
        startup_ids = (await db.execute(select(Startup.id).where(Startup.author_id == user.id))).scalars().all()
        deals_count    = (await db.execute(select(func.count(Deal.id)).where(Deal.startup_id.in_(startup_ids)))).scalar() if startup_ids else 0
        startups_count = len(startup_ids)
    else:
        deals_count    = (await db.execute(select(func.count(Deal.id)).where(Deal.buyer_id == user.id))).scalar()
        startups_count = 0
    # Load subscription
    from sqlalchemy import select as _sel
    subscription = (await db.execute(_sel(Subscription).where(Subscription.user_id == user.id))).scalar_one_or_none()
    return render(request, "user/profile.html", {
        "user": user, "wallet": wallet, "activity": activity,
        "unread_notifs": unread_notifs, "deals_count": deals_count, "startups_count": startups_count,
        "subscription": subscription,
    })


@router.post("/profile/update")
async def profile_update(request: Request, db: AsyncSession = Depends(get_db),
                         full_name: str = Form(""), bio: str = Form(""), phone: str = Form(""),
                         telegram: str = Form(""), website: str = Form(""), location: str = Form(""),
                         avatar: UploadFile = File(None)):
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", 302)
    user.full_name = full_name
    user.bio = bio; user.phone = phone; user.telegram = telegram
    user.website = website; user.location = location
    if avatar and avatar.filename:
        user.avatar = await save_image(avatar, "avatars", AVATAR_SIZE)
    await log_activity(db, user.id, "profile_update", "user", user.id)
    await db.commit()
    return RedirectResponse("/profile", 302)


# ── Notifications ──────────────────────────────────────────────────────────────

@router.get("/notifications", response_class=HTMLResponse)
async def notifications_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", 302)
    notifs = (await db.execute(
        select(Notification).where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc()).limit(50)
    )).scalars().all()
    await db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.is_read == False)
        .values(is_read=True)
    )
    await db.commit()
    return render(request, "user/notifications.html", {"user": user, "notifications": notifs})




# ── Notifications API (for bell dropdown) ──────────────────────────────────────

@router.get("/api/notifications")
async def api_notifications(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    if not user:
        return JSONResponse([], status_code=200)
    notifs = (await db.execute(
        select(Notification).where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc()).limit(20)
    )).scalars().all()
    return JSONResponse([{
        "id": n.id,
        "title": n.title,
        "body": n.body,
        "link": n.link,
        "is_read": n.is_read,
        "created_at": n.created_at.strftime("%d.%m %H:%M") if n.created_at else "",
    } for n in notifs])

# ── Wallet ─────────────────────────────────────────────────────────────────────

@router.get("/wallet", response_class=HTMLResponse)
async def wallet_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", 302)
    wallet = (await db.execute(
        select(Wallet).where(Wallet.user_id == user.id).options(selectinload(Wallet.transactions))
    )).scalar_one_or_none()
    return render(request, "user/wallet.html", {"user": user, "wallet": wallet})


@router.post("/wallet/deposit")
async def wallet_deposit(request: Request, db: AsyncSession = Depends(get_db),
                         amount: float = Form(...), method: str = Form("online")):
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", 302)
    if amount <= 0:
        raise HTTPException(400, "Сумма пополнения должна быть положительной")
    wallet = (await db.execute(select(Wallet).where(Wallet.user_id == user.id))).scalar_one_or_none()
    if not wallet:
        return RedirectResponse("/wallet", 302)
    wallet.balance += amount
    wallet.total_deposited += amount
    method_labels = {"online": "Картой", "qr": "QR / СБП", "bank": "Банковский перевод"}
    desc = "Пополнение баланса · " + method_labels.get(method, "Картой")
    tx = Transaction(wallet_id=wallet.id, type="deposit", amount=amount,
                     status=WithdrawStatus.approved, description=desc)
    db.add(tx)
    await db.flush()
    tx_id = tx.id
    await log_activity(db, user.id, "deposit", "wallet", wallet.id, detail=f"+{amount}")
    await db.commit()
    from services import email as mail
    if user.email:
        mail.send_deposit_receipt(user.email, user.username, user.id, tx_id,
                                  amount, method, wallet.balance)
    return RedirectResponse(f"/wallet/receipt/{tx_id}", 302)


@router.get("/wallet/receipt/{tx_id}", response_class=HTMLResponse)
async def wallet_receipt_page(tx_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", 302)
    tx = (await db.execute(
        select(Transaction).where(Transaction.id == tx_id)
    )).scalar_one_or_none()
    if not tx:
        raise HTTPException(404)
    wallet = (await db.execute(select(Wallet).where(Wallet.id == tx.wallet_id))).scalar_one_or_none()
    if not wallet or wallet.user_id != user.id:
        raise HTTPException(403)
    return render(request, "user/deposit_receipt.html", {"user": user, "tx": tx, "wallet": wallet})


@router.get("/wallet/receipt/{tx_id}/download")
async def wallet_receipt_download(tx_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    from fastapi.responses import Response
    from services.documents import generate_wallet_receipt_pdf
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", 302)
    tx = (await db.execute(
        select(Transaction).where(Transaction.id == tx_id)
    )).scalar_one_or_none()
    if not tx:
        raise HTTPException(404)
    wallet = (await db.execute(select(Wallet).where(Wallet.id == tx.wallet_id))).scalar_one_or_none()
    if not wallet or wallet.user_id != user.id:
        raise HTTPException(403)
    pdf_bytes = generate_wallet_receipt_pdf(
        tx_id=tx.id,
        username=user.username,
        user_id=user.id,
        user_email=user.email or "",
        amount=tx.amount,
        description=tx.description or "Пополнение баланса",
        balance_after=wallet.balance,
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="receipt_{tx_id}.pdf"'},
    )


# ── Support tickets ────────────────────────────────────────────────────────────

@router.get("/support", response_class=HTMLResponse)
async def support_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", 302)
    tickets = (await db.execute(
        select(SupportTicket).where(SupportTicket.user_id == user.id)
        .order_by(SupportTicket.created_at.desc())
    )).scalars().all()
    return render(request, "user/support.html", {"user": user, "tickets": tickets})


@router.post("/support/new")
async def support_new(request: Request, db: AsyncSession = Depends(get_db),
                      subject: str = Form(...), body: str = Form(...), priority: str = Form("medium")):
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", 302)
    from models.enums import NotifType
    from services import email as mail
    ticket = SupportTicket(user_id=user.id, subject=subject, body=body,
                           priority=TicketPriority(priority))
    db.add(ticket)
    await db.flush()
    staff = (await db.execute(
        select(User).where(User.role.in_([UserRole.admin, UserRole.manager]))
    )).scalars().all()
    for su in staff:
        await create_notification(db, su.id, NotifType.ticket,
                                  f"Новый тикет: {subject}",
                                  body[:100], "/admin/tickets")
    await log_activity(db, user.id, "ticket_created", "ticket", detail=subject)
    await db.commit()
    return RedirectResponse("/support", 302)


# ── My Startups ────────────────────────────────────────────────────────────────

@router.get("/my-startups", response_class=HTMLResponse)
async def my_startups(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", 302)
    startups = (await db.execute(
        select(Startup).where(Startup.author_id == user.id).order_by(Startup.created_at.desc())
    )).scalars().all()
    return render(request, "user/my_startups.html", {"user": user, "startups": startups})


@router.get("/my-startups/new", response_class=HTMLResponse)
async def new_startup_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", 302)
    return render(request, "user/startup_form.html", {"user": user, "startup": None, "error": None})


@router.post("/my-startups/new")
async def new_startup_post(request: Request, db: AsyncSession = Depends(get_db),
                           title: str = Form(...), category: str = Form(""), stage: str = Form(""),
                           tagline: str = Form(""), description: str = Form(""), emoji: str = Form("🚀"),
                           price: str = Form(""), revenue: str = Form(""), valuation: str = Form(""),
                           team_size: str = Form(""), founded_year: str = Form(""), website: str = Form(""),
                           cover: UploadFile = File(None)):
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", 302)
    # Проверка лимита стартапов по тарифу
    from routers.subscription import check_startup_limit
    ok_s, reason_s = await check_startup_limit(user, db)
    if not ok_s:
        return render(request, "user/startup_form.html", {"user": user, "startup": None, "error": reason_s})
    slug = f"{slugify(title)}-{uuid.uuid4().hex[:6]}"
    startup = Startup(
        author_id=user.id, title=title, slug=slug, category=category, stage=stage,
        tagline=tagline, description=description, emoji=emoji or "🚀",
        price=float(price) if price else None, revenue=float(revenue) if revenue else None,
        valuation=float(valuation) if valuation else None,
        team_size=int(team_size) if team_size else None,
        founded_year=int(founded_year) if founded_year else None,
        website=website, status=StartupStatus.active,
    )
    if cover and cover.filename:
        startup.cover_image = await save_image(cover, "covers", MAX_IMAGE_SIZE)
    db.add(startup)
    await log_activity(db, user.id, "startup_created", "startup", detail=title)
    await db.commit()
    return RedirectResponse("/my-startups", 302)


@router.get("/my-startups/{startup_id}/edit", response_class=HTMLResponse)
async def edit_startup_page(startup_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", 302)
    startup = (await db.execute(select(Startup).where(Startup.id == startup_id))).scalar_one_or_none()
    if not startup or (startup.author_id != user.id and user.role != UserRole.admin):
        raise HTTPException(403)
    return render(request, "user/startup_form.html", {"user": user, "startup": startup, "error": None})


@router.post("/my-startups/{startup_id}/edit")
async def edit_startup_post(startup_id: int, request: Request, db: AsyncSession = Depends(get_db),
                            title: str = Form(...), category: str = Form(""), stage: str = Form(""),
                            tagline: str = Form(""), description: str = Form(""), emoji: str = Form("🚀"),
                            price: str = Form(""), revenue: str = Form(""), valuation: str = Form(""),
                            team_size: str = Form(""), founded_year: str = Form(""), website: str = Form(""),
                            cover: UploadFile = File(None)):
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", 302)
    startup = (await db.execute(select(Startup).where(Startup.id == startup_id))).scalar_one_or_none()
    if not startup or (startup.author_id != user.id and user.role != UserRole.admin):
        raise HTTPException(403)
    startup.title = title; startup.category = category; startup.stage = stage
    startup.tagline = tagline; startup.description = description; startup.emoji = emoji or "🚀"
    startup.price    = float(price)    if price    else None
    startup.revenue  = float(revenue)  if revenue  else None
    startup.valuation = float(valuation) if valuation else None
    startup.team_size   = int(team_size)   if team_size   else None
    startup.founded_year = int(founded_year) if founded_year else None
    startup.website = website
    if cover and cover.filename:
        startup.cover_image = await save_image(cover, "covers", MAX_IMAGE_SIZE)
    await db.commit()
    return RedirectResponse("/my-startups", 302)


# ── My Deals ───────────────────────────────────────────────────────────────────

@router.get("/my-deals", response_class=HTMLResponse)
async def my_deals(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", 302)
    opts = [selectinload(Deal.startup), selectinload(Deal.buyer)]
    if user.role == UserRole.author:
        startup_ids = (await db.execute(select(Startup.id).where(Startup.author_id == user.id))).scalars().all()
        deals = (await db.execute(
            select(Deal).where(Deal.startup_id.in_(startup_ids))
            .options(*opts).order_by(Deal.created_at.desc())
        )).scalars().all() if startup_ids else []
    elif user.role in (UserRole.manager, UserRole.admin):
        deals = (await db.execute(select(Deal).options(*opts).order_by(Deal.created_at.desc()))).scalars().all()
    else:
        deals = (await db.execute(
            select(Deal).where(Deal.buyer_id == user.id).options(*opts).order_by(Deal.created_at.desc())
        )).scalars().all()
    return render(request, "user/my_deals.html", {"user": user, "deals": deals})


# ── Favorites ──────────────────────────────────────────────────────────────────

@router.get("/favorites", response_class=HTMLResponse)
async def favorites_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", 302)
    user_obj = (await db.execute(
        select(User).where(User.id == user.id).options(selectinload(User.favorite_startups))
    )).scalar_one()
    return render(request, "user/favorites.html", {"user": user, "startups": user_obj.favorite_startups})


@router.post("/favorites/toggle/{startup_id}")
async def toggle_favorite(startup_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    from models.user import favorites as fav_table
    user = await get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Не авторизован"}, 401)
    fav = (await db.execute(
        select(fav_table).where(fav_table.c.user_id == user.id, fav_table.c.startup_id == startup_id)
    )).first()
    if fav:
        await db.execute(fav_table.delete().where(
            fav_table.c.user_id == user.id, fav_table.c.startup_id == startup_id))
        is_fav = False
    else:
        await db.execute(fav_table.insert().values(user_id=user.id, startup_id=startup_id))
        is_fav = True
    await db.commit()
    return JSONResponse({"favorited": is_fav})


# ── Reviews ────────────────────────────────────────────────────────────────────

@router.post("/review/startup/{startup_id}")
async def add_review(startup_id: int, request: Request, db: AsyncSession = Depends(get_db),
                     rating: int = Form(...), comment: str = Form("")):
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", 302)
    startup = (await db.execute(select(Startup).where(Startup.id == startup_id))).scalar_one_or_none()
    if not startup:
        raise HTTPException(404)
    existing = (await db.execute(
        select(Review).where(Review.author_id == user.id, Review.startup_id == startup_id)
    )).scalar_one_or_none()
    if not existing:
        db.add(Review(author_id=user.id, target=ReviewTarget.startup,
                      startup_id=startup_id, rating=max(1, min(5, rating)), comment=comment))
        await db.commit()
    return RedirectResponse(f"/startup/{startup.slug}", 302)


# ── 2FA Setup ──────────────────────────────────────────────────────────────────

@router.post("/settings/2fa/setup")
async def twofa_setup(request: Request, db: AsyncSession = Depends(get_db)):
    import pyotp, qrcode, io, base64
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", 302)
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(user.email, issuer_name="StartHub")
    qr = qrcode.make(uri)
    buf = io.BytesIO()
    qr.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode()
    user.totp_secret = secret
    user.totp_enabled = False
    await db.commit()
    return render(request, "user/2fa_setup.html", {
        "user": user, "qr_code": qr_b64, "secret": secret, "error": None,
    })


@router.post("/settings/2fa/confirm")
async def twofa_confirm(request: Request, db: AsyncSession = Depends(get_db),
                        code: str = Form(...)):
    import pyotp, qrcode, io, base64
    user = await get_current_user(request, db)
    if not user or not user.totp_secret:
        return RedirectResponse("/profile", 302)
    totp = pyotp.TOTP(user.totp_secret)
    if not totp.verify(code.strip(), valid_window=1):
        uri = totp.provisioning_uri(user.email, issuer_name="StartHub")
        qr = qrcode.make(uri)
        buf = io.BytesIO()
        qr.save(buf, format="PNG")
        qr_b64 = base64.b64encode(buf.getvalue()).decode()
        return render(request, "user/2fa_setup.html", {
            "user": user, "qr_code": qr_b64, "secret": user.totp_secret,
            "error": "Неверный код. Проверьте приложение и попробуйте снова.",
        })
    user.totp_enabled = True
    await db.commit()
    return RedirectResponse("/profile?2fa=enabled", 302)


@router.post("/settings/2fa/disable")
async def twofa_disable(request: Request, db: AsyncSession = Depends(get_db),
                        code: str = Form(...)):
    import pyotp
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", 302)
    if user.totp_enabled and user.totp_secret:
        totp = pyotp.TOTP(user.totp_secret)
        if not totp.verify(code.strip(), valid_window=1):
            return RedirectResponse("/profile?2fa_error=wrong_code", 302)
    user.totp_enabled = False
    user.totp_secret = None
    await db.commit()
    return RedirectResponse("/profile?2fa=disabled", 302)
