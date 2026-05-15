from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.database import get_db
from core.security import get_current_user
from models.enums import StartupStatus, UserRole, DealStatus, ReviewTarget
from models.startup import Startup
from models.support import NewsPost, Review
from models.user import User, Transaction
from models.deal import Deal
from routers.deps import render

router = APIRouter()

# Пользователь считается онлайн, если последняя активность была не позднее N минут назад
ONLINE_THRESHOLD_MINUTES = 5


# ── Home ───────────────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def home(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)

    # Featured startups (на главной)
    featured = (await db.execute(
        select(Startup).where(Startup.status == StartupStatus.active)
        .options(selectinload(Startup.author))
        .order_by(Startup.is_featured.desc(), Startup.created_at.desc()).limit(6)
    )).scalars().all()

    # ── Реальная статистика для hero и numbers ──
    total_startups = (await db.execute(
        select(func.count(Startup.id)).where(Startup.status == StartupStatus.active)
    )).scalar() or 0

    # Суммарный объём закрытых сделок
    total_volume = (await db.execute(
        select(func.coalesce(func.sum(Deal.final_amount), 0.0))
        .where(Deal.status == DealStatus.closed_ok)
    )).scalar() or 0

    # Активные инвесторы — те, кто заходил за последние 30 дней
    activity_cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    active_investors = (await db.execute(
        select(func.count(User.id))
        .where(User.role == UserRole.buyer)
        .where(User.is_banned == False)
        .where(User.last_seen >= activity_cutoff)
    )).scalar() or 0

    # Если ничего нет — хотя бы общее количество инвесторов
    if active_investors == 0:
        active_investors = (await db.execute(
            select(func.count(User.id)).where(User.role == UserRole.buyer).where(User.is_banned == False)
        )).scalar() or 0

    # Средний срок закрытия сделки в днях
    closed_deals = (await db.execute(
        select(Deal.created_at, Deal.closed_at).where(
            Deal.status == DealStatus.closed_ok,
            Deal.closed_at.isnot(None),
        )
    )).all()
    if closed_deals:
        avg_days = sum((d.closed_at - d.created_at).days for d in closed_deals) / len(closed_deals)
        avg_days = max(1, int(round(avg_days)))
    else:
        avg_days = 23  # fallback

    # ── Реальные категории с подсчётом ──
    cat_emojis = {
        "AI / ML": "🤖", "FinTech": "💳", "HealthTech": "💊", "GreenTech": "🌱",
        "EdTech": "📚", "Logistics": "🚛", "SaaS": "☁️", "SaaS / B2B": "☁️",
        "E-commerce": "🛒", "Blockchain": "⛓️", "Mobile": "📱",
    }
    cat_rows = (await db.execute(
        select(Startup.category, func.count(Startup.id))
        .where(Startup.status == StartupStatus.active)
        .where(Startup.category.isnot(None))
        .group_by(Startup.category)
        .order_by(func.count(Startup.id).desc())
        .limit(8)
    )).all()
    categories = [
        {"name": name, "count": cnt, "emoji": cat_emojis.get(name, "🚀")}
        for name, cnt in cat_rows if name
    ]

    # ── Инвесторы онлайн (реально активные сейчас) ──
    online_cutoff = datetime.now(timezone.utc) - timedelta(minutes=ONLINE_THRESHOLD_MINUTES)
    online_investors = (await db.execute(
        select(User).where(
            User.role == UserRole.buyer,
            User.is_banned == False,
            User.last_seen >= online_cutoff,
        ).order_by(User.last_seen.desc()).limit(8)
    )).scalars().all()

    # ── Реальные отзывы для главной (featured) ──
    landing_reviews = (await db.execute(
        select(Review)
        .where(Review.is_visible == True)
        .where(Review.rating >= 4)
        .options(selectinload(Review.author), selectinload(Review.startup))
        .order_by(Review.created_at.desc())
        .limit(12)
    )).scalars().all()

    return render(request, "index.html", {
        "user": user,
        "startups": featured,
        "stats": {
            "total_startups": total_startups,
            "total_volume": total_volume,
            "active_investors": active_investors,
            "avg_days": avg_days,
        },
        "categories": categories,
        "online_investors": online_investors,
        "landing_reviews": landing_reviews,
    })


# ── Catalog ────────────────────────────────────────────────────────────────────

@router.get("/catalog", response_class=HTMLResponse)
async def catalog(request: Request, db: AsyncSession = Depends(get_db),
                  q: str = "", category: str = "", stage: str = "", sort: str = "newest"):
    user = await get_current_user(request, db)
    query = (select(Startup).where(Startup.status == StartupStatus.active)
             .options(selectinload(Startup.author)))
    if q:
        query = query.where(or_(Startup.title.ilike(f"%{q}%"), Startup.tagline.ilike(f"%{q}%")))
    if category:
        query = query.where(Startup.category == category)
    if stage:
        query = query.where(Startup.stage == stage)
    query = query.order_by(
        Startup.price.asc()        if sort == "price_asc"  else
        Startup.price.desc()       if sort == "price_desc" else
        Startup.created_at.desc()
    )
    startups = (await db.execute(query)).scalars().all()
    categories = ["AI / ML", "FinTech", "HealthTech", "GreenTech", "EdTech", "Logistics", "SaaS", "E-commerce"]
    stages     = ["Pre-seed", "Seed", "Series A", "Series B", "Series C"]
    return render(request, "catalog.html", {
        "user": user, "startups": startups, "categories": categories, "stages": stages,
        "q": q, "selected_cat": category, "selected_stage": stage, "sort": sort,
    })


# ── Startup detail ─────────────────────────────────────────────────────────────

@router.get("/startup/{slug}", response_class=HTMLResponse)
async def startup_detail(slug: str, request: Request, db: AsyncSession = Depends(get_db)):
    from models.user import favorites as fav_table
    user = await get_current_user(request, db)
    result = await db.execute(
        select(Startup).where(Startup.slug == slug)
        .options(
            selectinload(Startup.author),
            selectinload(Startup.tags),
            selectinload(Startup.reviews).selectinload(Review.author),
        )
    )
    startup = result.scalar_one_or_none()
    if not startup:
        from fastapi import HTTPException
        raise HTTPException(404, "Стартап не найден")
    startup.views_count = (startup.views_count or 0) + 1
    await db.commit()
    is_favorited = False
    if user:
        fav = (await db.execute(
            select(fav_table).where(fav_table.c.user_id == user.id, fav_table.c.startup_id == startup.id)
        )).first()
        is_favorited = fav is not None
    visible = [r for r in startup.reviews if r.is_visible]
    avg_rating = round(sum(r.rating for r in visible) / len(visible), 1) if visible else None
    return render(request, "startup_detail.html", {
        "user": user, "startup": startup, "is_favorited": is_favorited, "avg_rating": avg_rating,
    })


# ── News / Blog ────────────────────────────────────────────────────────────────

@router.get("/news", response_class=HTMLResponse)
async def news_list(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    posts = (await db.execute(
        select(NewsPost).where(NewsPost.is_published == True, NewsPost.is_blog == False)
        .order_by(NewsPost.created_at.desc())
    )).scalars().all()
    return render(request, "news.html", {"user": user, "posts": posts})


@router.get("/blog", response_class=HTMLResponse)
async def blog_list(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    posts = (await db.execute(
        select(NewsPost).where(NewsPost.is_published == True, NewsPost.is_blog == True)
        .order_by(NewsPost.created_at.desc())
    )).scalars().all()
    return render(request, "blog.html", {"user": user, "posts": posts})


# ── Static pages ───────────────────────────────────────────────────────────────

@router.get("/faq",     response_class=HTMLResponse)
async def faq(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    return render(request, "faq.html", {"user": user})

@router.get("/about",   response_class=HTMLResponse)
async def about(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    return render(request, "about.html", {"user": user})

@router.get("/terms",   response_class=HTMLResponse)
async def terms(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    return render(request, "terms.html", {"user": user})

@router.get("/pricing", response_class=HTMLResponse)
async def pricing(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    return render(request, "pages/pricing.html", {"user": user})

@router.get("/investors", response_class=HTMLResponse)
async def investors_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    investors = (await db.execute(
        select(User).where(User.role == UserRole.buyer, User.is_active == True)
        .order_by(User.created_at.desc()).limit(20)
    )).scalars().all()
    return render(request, "pages/investors.html", {"user": user, "investors": investors})

@router.get("/contact", response_class=HTMLResponse)
async def contact(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    return render(request, "pages/contact.html", {"user": user, "sent": False})

@router.post("/contact")
async def contact_post(request: Request, db: AsyncSession = Depends(get_db),
                       name: str = Form(""), email: str = Form(""), message: str = Form("")):
    user = await get_current_user(request, db)
    return render(request, "pages/contact.html", {"user": user, "sent": True})
