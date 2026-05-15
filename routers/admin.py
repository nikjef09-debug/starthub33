import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.database import get_db
from core.security import get_current_user
from models.enums import (
    DealStatus, NotifType, TicketStatus, UserRole, WithdrawStatus,
)
from models.deal import Deal
from models.startup import Startup
from models.support import NewsPost, Review, SupportTicket
from models.user import User, ActivityLog, Transaction
from services.notifications import create_notification, log_activity
from utils.helpers import slugify
from routers.deps import render

router = APIRouter(prefix="/admin")


async def _require_admin(request: Request, db: AsyncSession) -> User:
    user = await get_current_user(request, db)
    if not user or user.role != UserRole.admin:
        raise HTTPException(403, "Только для администраторов")
    return user


async def _badges(db: AsyncSession) -> dict:
    """Aggregated counts for sidebar badges (active deals, open tickets)."""
    active_deals = (await db.execute(
        select(func.count(Deal.id)).where(Deal.status.in_([DealStatus.pending, DealStatus.active, DealStatus.documents]))
    )).scalar() or 0
    open_tickets = (await db.execute(
        select(func.count(SupportTicket.id)).where(SupportTicket.status == TicketStatus.open)
    )).scalar() or 0
    return {"active_deals": active_deals, "open_tickets": open_tickets}


# ── Dashboard ──────────────────────────────────────────────────────────────────

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    admin = await _require_admin(request, db)
    badges = await _badges(db)

    user_count    = (await db.execute(select(func.count(User.id)))).scalar()
    startup_count = (await db.execute(select(func.count(Startup.id)))).scalar()
    deal_count    = (await db.execute(select(func.count(Deal.id)))).scalar()
    active_deals  = badges["active_deals"]
    revenue_total = (await db.execute(
        select(func.sum(Transaction.amount)).where(
            Transaction.type == "deposit", Transaction.status == WithdrawStatus.approved
        )
    )).scalar() or 0
    recent_users  = (await db.execute(select(User).order_by(User.created_at.desc()).limit(8))).scalars().all()
    recent_deals  = (await db.execute(
        select(Deal).options(selectinload(Deal.startup), selectinload(Deal.buyer))
        .order_by(Deal.created_at.desc()).limit(8)
    )).scalars().all()
    recent_logs   = (await db.execute(
        select(ActivityLog).options(selectinload(ActivityLog.user))
        .order_by(ActivityLog.created_at.desc()).limit(15)
    )).scalars().all()

    return render(request, "admin/dashboard.html", {
        "user": admin, **badges,
        "user_count": user_count, "startup_count": startup_count,
        "deal_count": deal_count, "active_deals": active_deals,
        "revenue_total": revenue_total, "recent_users": recent_users,
        "recent_deals": recent_deals, "recent_logs": recent_logs,
    })


# ── Users ──────────────────────────────────────────────────────────────────────

@router.get("/users", response_class=HTMLResponse)
async def users_list(request: Request, db: AsyncSession = Depends(get_db), q: str = "", role: str = ""):
    admin = await _require_admin(request, db)
    badges = await _badges(db)
    query = select(User).order_by(User.created_at.desc())
    if q:
        query = query.where(or_(
            User.email.ilike(f"%{q}%"), User.username.ilike(f"%{q}%"), User.full_name.ilike(f"%{q}%")
        ))
    if role:
        query = query.where(User.role == UserRole(role))
    users = (await db.execute(query)).scalars().all()
    return render(request, "admin/users.html", {
        "user": admin, **badges, "users": users, "q": q, "role_filter": role,
        "now_ts": datetime.now(timezone.utc).timestamp(),
    })


@router.post("/users/{user_id}/role")
async def change_role(user_id: int, request: Request, db: AsyncSession = Depends(get_db), role: str = Form(...)):
    admin = await _require_admin(request, db)
    target = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if target:
        target.role = UserRole(role)
        await log_activity(db, admin.id, "role_changed", "user", user_id, detail=f"→ {role}")
        await db.commit()
    return RedirectResponse(f"/admin/users/{user_id}", 302)


@router.post("/users/{user_id}/ban")
async def ban_user(user_id: int, request: Request, db: AsyncSession = Depends(get_db),
                   reason: str = Form("Нарушение правил")):
    admin = await _require_admin(request, db)
    target = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if target and target.role != UserRole.admin:
        target.is_banned = not target.is_banned
        target.ban_reason = reason if target.is_banned else None
        await log_activity(db, admin.id, "user_ban" if target.is_banned else "user_unban", "user", user_id)
        await db.commit()
    return RedirectResponse("/admin/users", 302)


@router.get("/users/{user_id}", response_class=HTMLResponse)
async def user_detail(user_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    admin = await _require_admin(request, db)
    badges = await _badges(db)
    target = (await db.execute(
        select(User).where(User.id == user_id).options(
            selectinload(User.startups), selectinload(User.deals_as_buyer),
            selectinload(User.activity_logs), selectinload(User.wallet),
        )
    )).scalar_one_or_none()
    if not target:
        raise HTTPException(404)
    return render(request, "admin/user_detail.html", {"user": admin, **badges, "target": target})


# ── Startups ───────────────────────────────────────────────────────────────────

@router.get("/startups", response_class=HTMLResponse)
async def startups_list(request: Request, db: AsyncSession = Depends(get_db)):
    admin = await _require_admin(request, db)
    badges = await _badges(db)
    startups = (await db.execute(
        select(Startup).options(selectinload(Startup.author)).order_by(Startup.created_at.desc())
    )).scalars().all()
    return render(request, "admin/startups.html", {"user": admin, **badges, "startups": startups})


@router.post("/startups/{startup_id}/feature")
async def feature_startup(startup_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    await _require_admin(request, db)
    s = (await db.execute(select(Startup).where(Startup.id == startup_id))).scalar_one_or_none()
    if s:
        s.is_featured = not s.is_featured
        await db.commit()
    return RedirectResponse("/admin/startups", 302)


@router.post("/startups/{startup_id}/verify")
async def verify_startup(startup_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    await _require_admin(request, db)
    s = (await db.execute(select(Startup).where(Startup.id == startup_id))).scalar_one_or_none()
    if s:
        s.is_verified = not s.is_verified
        await db.commit()
    return RedirectResponse("/admin/startups", 302)


# ── Deals ──────────────────────────────────────────────────────────────────────

@router.get("/deals", response_class=HTMLResponse)
async def deals_list(request: Request, db: AsyncSession = Depends(get_db)):
    admin = await _require_admin(request, db)
    badges = await _badges(db)
    deals = (await db.execute(
        select(Deal).options(selectinload(Deal.startup), selectinload(Deal.buyer))
        .order_by(Deal.created_at.desc())
    )).scalars().all()
    return render(request, "admin/deals.html", {"user": admin, **badges, "deals": deals})


# ── News ───────────────────────────────────────────────────────────────────────

@router.get("/news", response_class=HTMLResponse)
async def news_list(request: Request, db: AsyncSession = Depends(get_db)):
    admin = await _require_admin(request, db)
    badges = await _badges(db)
    posts = (await db.execute(select(NewsPost).order_by(NewsPost.created_at.desc()))).scalars().all()
    return render(request, "admin/news.html", {"user": admin, **badges, "posts": posts})


@router.get("/news/new", response_class=HTMLResponse)
async def news_new_page(request: Request, db: AsyncSession = Depends(get_db)):
    admin = await _require_admin(request, db)
    badges = await _badges(db)
    return render(request, "admin/news_form.html", {"user": admin, **badges, "post": None})


@router.post("/news/new")
async def news_create(request: Request, db: AsyncSession = Depends(get_db),
                      title: str = Form(...), body: str = Form(""), excerpt: str = Form(""),
                      is_blog: str = Form("0"), is_published: str = Form("0"), category: str = Form("")):
    admin = await _require_admin(request, db)
    slug = f"{slugify(title)}-{uuid.uuid4().hex[:6]}"
    db.add(NewsPost(
        author_id=admin.id, title=title, slug=slug, body=body, excerpt=excerpt,
        is_blog=is_blog == "1", is_published=is_published == "1", category=category,
    ))
    await db.commit()
    return RedirectResponse("/admin/news", 302)


# ── Tickets ────────────────────────────────────────────────────────────────────

@router.get("/tickets", response_class=HTMLResponse)
async def tickets_list(request: Request, db: AsyncSession = Depends(get_db)):
    admin = await _require_admin(request, db)
    badges = await _badges(db)
    tickets = (await db.execute(
        select(SupportTicket).options(selectinload(SupportTicket.user))
        .order_by(SupportTicket.created_at.desc())
    )).scalars().all()
    return render(request, "admin/tickets.html", {"user": admin, **badges, "tickets": tickets})


@router.post("/tickets/{ticket_id}/reply")
async def ticket_reply(ticket_id: int, request: Request, db: AsyncSession = Depends(get_db),
                       reply: str = Form(...), status: str = Form("in_progress")):
    admin = await _require_admin(request, db)
    ticket = (await db.execute(select(SupportTicket).where(SupportTicket.id == ticket_id))).scalar_one_or_none()
    if ticket:
        ticket.manager_reply = reply
        ticket.assigned_to   = admin.id
        ticket.status        = TicketStatus(status)
        ticket.replied_at    = datetime.now(timezone.utc)
        if status == "closed":
            ticket.closed_at = datetime.now(timezone.utc)
        await create_notification(db, ticket.user_id, NotifType.system,
                                  "Ответ на ваш тикет", reply[:100], "/support")
        await db.commit()
    return RedirectResponse("/admin/tickets", 302)


# ── Reviews ────────────────────────────────────────────────────────────────────

@router.get("/reviews", response_class=HTMLResponse)
async def reviews_list(request: Request, db: AsyncSession = Depends(get_db)):
    admin = await _require_admin(request, db)
    badges = await _badges(db)
    reviews = (await db.execute(
        select(Review).options(selectinload(Review.author), selectinload(Review.startup))
        .order_by(Review.created_at.desc())
    )).scalars().all()
    return render(request, "admin/reviews.html", {"user": admin, **badges, "reviews": reviews})


@router.post("/reviews/{review_id}/toggle")
async def toggle_review(review_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    await _require_admin(request, db)
    r = (await db.execute(select(Review).where(Review.id == review_id))).scalar_one_or_none()
    if r:
        r.is_visible = not r.is_visible
        await db.commit()
    return RedirectResponse("/admin/reviews", 302)


@router.post("/reviews/{review_id}/toggle-landing")
async def toggle_review_landing(review_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    await _require_admin(request, db)
    r = (await db.execute(select(Review).where(Review.id == review_id))).scalar_one_or_none()
    if r:
        r.is_featured_on_landing = not r.is_featured_on_landing
        await db.commit()
    return RedirectResponse("/admin/reviews", 302)


# ── Analytics ──────────────────────────────────────────────────────────────────

@router.get("/analytics", response_class=HTMLResponse)
async def analytics(request: Request, db: AsyncSession = Depends(get_db)):
    admin = await _require_admin(request, db)
    badges = await _badges(db)
    cat_stats  = {r[0]: r[1] for r in (await db.execute(
        select(Startup.category, func.count(Startup.id)).group_by(Startup.category)
    )).all() if r[0]}
    deal_stats = {r[0].value: r[1] for r in (await db.execute(
        select(Deal.status, func.count(Deal.id)).group_by(Deal.status)
    )).all()}
    role_stats = {r[0].value: r[1] for r in (await db.execute(
        select(User.role, func.count(User.id)).group_by(User.role)
    )).all()}
    top_startups = (await db.execute(
        select(Startup).options(selectinload(Startup.author))
        .order_by(Startup.views_count.desc()).limit(10)
    )).scalars().all()
    recent_tx = (await db.execute(
        select(Transaction).order_by(Transaction.created_at.desc()).limit(20)
    )).scalars().all()
    return render(request, "admin/analytics.html", {
        "user": admin, **badges, "cat_stats": cat_stats, "deal_stats": deal_stats,
        "role_stats": role_stats, "top_startups": top_startups, "recent_tx": recent_tx,
    })


# ── Logs ───────────────────────────────────────────────────────────────────────

@router.get("/logs", response_class=HTMLResponse)
async def logs(request: Request, db: AsyncSession = Depends(get_db)):
    admin = await _require_admin(request, db)
    badges = await _badges(db)
    logs_list = (await db.execute(
        select(ActivityLog).options(selectinload(ActivityLog.user))
        .order_by(ActivityLog.created_at.desc()).limit(200)
    )).scalars().all()
    return render(request, "admin/logs.html", {"user": admin, **badges, "logs": logs_list})


# ── Settings ───────────────────────────────────────────────────────────────────

@router.get("/settings", response_class=HTMLResponse)
async def settings(request: Request, db: AsyncSession = Depends(get_db)):
    admin = await _require_admin(request, db)
    badges = await _badges(db)
    return render(request, "admin/settings.html", {"user": admin, **badges})
