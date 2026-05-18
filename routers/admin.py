import json
import uuid
import asyncio
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy import func, select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.database import get_db
from core.security import get_current_user
from models.enums import (
    DealStatus, NotifType, TicketStatus, UserRole, WithdrawStatus,
)
from models.deal import Deal, Payment, DealDocument
from models.startup import Startup
from models.support import (
    NewsPost, Review, SupportTicket, CustomRole, EmailCampaign,
    PlatformSetting, RoleConfig, PERM_KEYS, PERM_LABELS, DEFAULT_ROLE_CONFIGS,
)
from models.user import User, ActivityLog, Transaction
from services.notifications import create_notification, log_activity
from services.settings import get_all_settings, set_setting, TOGGLE_KEYS, TEXT_KEYS
from services import email as mail
from utils.helpers import slugify, save_image
from routers.deps import render

router = APIRouter(prefix="/admin")


async def _require_admin(request: Request, db: AsyncSession) -> User:
    user = await get_current_user(request, db)
    if not user or user.role not in (UserRole.admin, UserRole.developer):
        raise HTTPException(403, "Только для администраторов")
    return user


async def _badges(db: AsyncSession) -> dict:
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
    custom_roles = (await db.execute(select(CustomRole).order_by(CustomRole.name))).scalars().all()
    return render(request, "admin/users.html", {
        "user": admin, **badges, "users": users, "q": q, "role_filter": role,
        "now_ts": datetime.now(timezone.utc).timestamp(),
        "custom_roles": custom_roles,
    })


@router.post("/users/{user_id}/role")
async def change_role(user_id: int, request: Request, db: AsyncSession = Depends(get_db), role: str = Form(...)):
    admin = await _require_admin(request, db)
    target = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if target:
        valid_roles = {r.value for r in UserRole}
        if role not in valid_roles:
            # Пользовательская роль — не может быть назначена как системная роль
            return RedirectResponse(f"/admin/users/{user_id}?error=custom_role_not_assignable", 302)
        target.role = UserRole(role)
        await log_activity(db, admin.id, "role_changed", "user", user_id, detail=f"→ {role}")
        await db.commit()
    return RedirectResponse(f"/admin/users/{user_id}", 302)



@router.post("/users/{user_id}/custom-role")
async def assign_custom_role(user_id: int, request: Request, db: AsyncSession = Depends(get_db),
                              custom_role_name: str = Form(...)):
    admin = await _require_admin(request, db)
    target = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not target:
        raise HTTPException(404)
    if custom_role_name == "__none__":
        target.custom_role_name = None
    else:
        # Проверяем что такая роль существует
        from models.support import CustomRole
        cr = (await db.execute(select(CustomRole).where(CustomRole.name == custom_role_name))).scalar_one_or_none()
        if not cr:
            raise HTTPException(400, "Роль не найдена")
        target.custom_role_name = custom_role_name
    await log_activity(db, admin.id, "custom_role_assigned", "user", user_id, detail=f"→ {custom_role_name}")
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
            selectinload(User.tickets),
        )
    )).scalar_one_or_none()
    if not target:
        raise HTTPException(404)
    custom_roles = (await db.execute(select(CustomRole).order_by(CustomRole.name))).scalars().all()
    # Активные права текущей кастомной роли для отображения
    cur_cr_active_perms: list[str] = []
    if target.custom_role_name:
        for cr in custom_roles:
            if cr.name == target.custom_role_name:
                try:
                    perms = json.loads(cr.permissions)
                    cur_cr_active_perms = [k for k, v in perms.items() if v]
                except Exception:
                    pass
                break
    return render(request, "admin/user_detail.html", {
        "user": admin, **badges, "target": target,
        "custom_roles": custom_roles,
        "all_roles": [r.value for r in UserRole],
        "cur_cr_active_perms": cur_cr_active_perms,
    })


@router.post("/users/{user_id}/permissions")
async def update_permissions(user_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """Детальное обновление прав пользователя через форму."""
    admin = await _require_admin(request, db)
    target = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not target:
        raise HTTPException(404)
    form = await request.form()
    new_role = form.get("role")
    if new_role and new_role in [r.value for r in UserRole]:
        target.role = UserRole(new_role)
    is_verified = form.get("is_verified") == "1"
    is_active   = form.get("is_active")   == "1"
    target.is_verified = is_verified
    target.is_active   = is_active
    await log_activity(db, admin.id, "permissions_updated", "user", user_id,
                       detail=f"role={new_role}, verified={is_verified}, active={is_active}")
    await db.commit()
    return RedirectResponse(f"/admin/users/{user_id}", 302)


# ── Roles ──────────────────────────────────────────────────────────────────────

def _parse_perms(raw: str) -> dict:
    try:
        return json.loads(raw)
    except Exception:
        return {}


@router.get("/roles", response_class=HTMLResponse)
async def roles_list(request: Request, db: AsyncSession = Depends(get_db)):
    admin = await _require_admin(request, db)
    badges = await _badges(db)

    # Основные роли
    base_configs_raw = (await db.execute(select(RoleConfig))).scalars().all()
    base_by_name = {rc.role_name: rc for rc in base_configs_raw}

    # Если записи ещё не созданы (первый запуск без init_role_configs) — создаём на лету
    for role_name, defaults in DEFAULT_ROLE_CONFIGS.items():
        if role_name not in base_by_name:
            rc = RoleConfig(
                role_name=role_name,
                label=defaults["label"],
                description=defaults["description"],
                visible_at_registration=defaults["visible_at_registration"],
                permissions=json.dumps(defaults["permissions"]),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(rc)
            base_by_name[role_name] = rc
    await db.flush()

    base_roles = []
    for role_name in ("buyer", "author", "manager", "admin", "developer"):
        rc = base_by_name.get(role_name)
        if rc:
            base_roles.append({"config": rc, "perms": _parse_perms(rc.permissions)})

    # Дополнительные наборы прав (CustomRole)
    presets = (await db.execute(select(CustomRole).order_by(CustomRole.created_at.desc()))).scalars().all()
    presets_parsed = [{"role": p, "perms": _parse_perms(p.permissions)} for p in presets]

    await db.commit()
    return render(request, "admin/roles.html", {
        "user": admin, **badges,
        "base_roles": base_roles,
        "presets": presets_parsed,
        "perm_keys": PERM_KEYS,
        "PERM_LABELS": PERM_LABELS,
    })


@router.post("/roles/base/{role_name}/save")
async def save_base_role(role_name: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Сохранить конфигурацию основной роли."""
    admin = await _require_admin(request, db)
    if role_name not in DEFAULT_ROLE_CONFIGS:
        raise HTTPException(400, "Неизвестная роль")
    rc = (await db.execute(select(RoleConfig).where(RoleConfig.role_name == role_name))).scalar_one_or_none()
    if not rc:
        raise HTTPException(404)
    form = await request.form()
    rc.label       = form.get("label", rc.label).strip() or rc.label
    rc.description = form.get("description", "").strip()
    rc.visible_at_registration = form.get("visible_at_registration") == "1"
    perms = {k: (form.get(f"perm_{k}") == "1") for k in PERM_KEYS}
    rc.permissions = json.dumps(perms)
    rc.updated_at  = datetime.now(timezone.utc)
    await log_activity(db, admin.id, "role_config_saved", "role_config", detail=role_name)
    await db.commit()
    return RedirectResponse("/admin/roles", 302)


@router.post("/roles/preset/create")
async def create_preset_role(request: Request, db: AsyncSession = Depends(get_db)):
    """Создать дополнительный набор прав."""
    admin = await _require_admin(request, db)
    form  = await request.form()
    name  = form.get("name", "").strip().lower().replace(" ", "_")
    label = form.get("label", "").strip()
    if not name or not label:
        return RedirectResponse("/admin/roles", 302)
    perms = {k: (form.get(f"perm_{k}") == "1") for k in PERM_KEYS}
    db.add(CustomRole(name=name, label=label, permissions=json.dumps(perms)))
    await log_activity(db, admin.id, "preset_role_created", "custom_role", detail=name)
    await db.commit()
    return RedirectResponse("/admin/roles", 302)


@router.post("/roles/preset/{role_id}/delete")
async def delete_preset_role(role_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    admin = await _require_admin(request, db)
    role  = (await db.execute(select(CustomRole).where(CustomRole.id == role_id))).scalar_one_or_none()
    if role:
        await db.delete(role)
        await db.commit()
    return RedirectResponse("/admin/roles", 302)


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


@router.post("/startups/{startup_id}/status")
async def change_startup_status(startup_id: int, request: Request, db: AsyncSession = Depends(get_db),
                                 status: str = Form(...)):
    await _require_admin(request, db)
    s = (await db.execute(select(Startup).where(Startup.id == startup_id))).scalar_one_or_none()
    if s:
        from models.enums import StartupStatus
        try:
            s.status = StartupStatus(status)
            await db.commit()
        except ValueError:
            pass
    return RedirectResponse("/admin/startups", 302)


@router.post("/startups/{startup_id}/delete")
async def delete_startup(startup_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    await _require_admin(request, db)
    s = (await db.execute(select(Startup).where(Startup.id == startup_id))).scalar_one_or_none()
    if not s:
        return RedirectResponse("/admin/startups", 302)

    # Удаляем связанные данные вручную (избегаем FK constraint errors)
    import aiosqlite
    from core.config import BASE_DIR
    db_path = str(BASE_DIR / "starthub.db")

    async with aiosqlite.connect(db_path) as raw:
        await raw.execute("PRAGMA foreign_keys = OFF")
        # Удаляем из избранного
        await raw.execute("DELETE FROM favorites WHERE startup_id = ?", (startup_id,))
        # Удаляем отзывы
        await raw.execute("DELETE FROM reviews WHERE startup_id = ?", (startup_id,))
        # Получаем deal_ids этого стартапа
        cur = await raw.execute("SELECT id FROM deals WHERE startup_id = ?", (startup_id,))
        deal_ids = [row[0] for row in await cur.fetchall()]
        for deal_id in deal_ids:
            await raw.execute("DELETE FROM messages WHERE deal_id = ?", (deal_id,))
            await raw.execute("DELETE FROM deal_documents WHERE deal_id = ?", (deal_id,))
            await raw.execute("DELETE FROM payments WHERE deal_id = ?", (deal_id,))
        if deal_ids:
            placeholders = ",".join("?" * len(deal_ids))
            await raw.execute(f"DELETE FROM deals WHERE id IN ({placeholders})", deal_ids)
        # Удаляем сам стартап
        await raw.execute("DELETE FROM startups WHERE id = ?", (startup_id,))
        await raw.execute("PRAGMA foreign_keys = ON")
        await raw.commit()

    return RedirectResponse("/admin/startups", 302)


@router.post("/startups/{startup_id}/upload-cover")
async def admin_startup_upload_cover(
    startup_id: int, request: Request,
    db: AsyncSession = Depends(get_db),
    cover: UploadFile = File(None),
):
    from core.config import MAX_IMAGE_SIZE
    admin = await _require_admin(request, db)
    s = (await db.execute(select(Startup).where(Startup.id == startup_id))).scalar_one_or_none()
    if not s:
        raise HTTPException(404)
    if cover and cover.filename:
        s.cover_image = await save_image(cover, "startups", MAX_IMAGE_SIZE)
        await db.commit()
    return RedirectResponse("/admin/startups", 302)


# ── Deals (admin view + edit) ──────────────────────────────────────────────────

@router.get("/deals", response_class=HTMLResponse)
async def deals_list(request: Request, db: AsyncSession = Depends(get_db)):
    admin = await _require_admin(request, db)
    badges = await _badges(db)
    deals = (await db.execute(
        select(Deal).options(selectinload(Deal.startup), selectinload(Deal.buyer))
        .order_by(Deal.created_at.desc())
    )).scalars().all()
    return render(request, "admin/deals.html", {"user": admin, **badges, "deals": deals})


@router.get("/deals/{deal_id}", response_class=HTMLResponse)
async def deal_detail(deal_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """Детальная страница сделки для администратора."""
    admin = await _require_admin(request, db)
    badges = await _badges(db)
    deal = (await db.execute(
        select(Deal).where(Deal.id == deal_id).options(
            selectinload(Deal.startup).selectinload(Startup.author),
            selectinload(Deal.buyer),
            selectinload(Deal.managers),
            selectinload(Deal.messages),
            selectinload(Deal.documents),
            selectinload(Deal.payments),
        )
    )).scalar_one_or_none()
    if not deal:
        raise HTTPException(404)
    all_managers = (await db.execute(
        select(User).where(User.role.in_([UserRole.manager, UserRole.admin]))
    )).scalars().all()
    return render(request, "admin/deal_detail.html", {
        "user": admin, **badges, "deal": deal,
        "all_managers": all_managers,
        "deal_statuses": [s.value for s in DealStatus],
    })


@router.post("/deals/{deal_id}/edit")
async def deal_edit(deal_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    admin = await _require_admin(request, db)
    deal = (await db.execute(select(Deal).where(Deal.id == deal_id))).scalar_one_or_none()
    if not deal:
        raise HTTPException(404)
    form = await request.form()
    new_status = form.get("status")
    final_amount = form.get("final_amount")
    note = form.get("note", "")
    if new_status:
        deal.status = DealStatus(new_status)
        if new_status in ("closed_ok", "closed_fail"):
            deal.closed_at = datetime.now(timezone.utc)
    if final_amount:
        try:
            deal.final_amount = float(final_amount)
        except ValueError:
            pass
    deal.note = note
    await log_activity(db, admin.id, "deal_edited", "deal", deal_id,
                       detail=f"status={new_status}, amount={final_amount}")
    await db.commit()
    return RedirectResponse(f"/admin/deals/{deal_id}", 302)


@router.post("/deals/{deal_id}/assign-manager")
async def assign_manager(deal_id: int, request: Request, db: AsyncSession = Depends(get_db),
                          manager_id: int = Form(...)):
    admin = await _require_admin(request, db)
    deal = (await db.execute(
        select(Deal).where(Deal.id == deal_id).options(selectinload(Deal.managers))
    )).scalar_one_or_none()
    manager = (await db.execute(select(User).where(User.id == manager_id))).scalar_one_or_none()
    if deal and manager:
        if manager not in deal.managers:
            deal.managers.append(manager)
        # Уведомление менеджеру
        await create_notification(db, manager_id, NotifType.deal_new,
                                  "Вас назначили менеджером сделки",
                                  f"Сделка #{deal_id}", f"/deal/{deal_id}")
        await db.commit()
    return RedirectResponse(f"/admin/deals/{deal_id}", 302)


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
                      is_blog: str = Form("0"), is_published: str = Form("0"), category: str = Form(""),
                      cover: UploadFile = File(None)):
    admin = await _require_admin(request, db)
    from core.config import MAX_IMAGE_SIZE
    slug = f"{slugify(title)}-{uuid.uuid4().hex[:6]}"
    post = NewsPost(
        author_id=admin.id, title=title, slug=slug, body=body, excerpt=excerpt,
        is_blog=is_blog == "1", is_published=is_published == "1", category=category,
    )
    if cover and cover.filename:
        post.cover = await save_image(cover, "news", MAX_IMAGE_SIZE)
    db.add(post)
    await db.commit()
    return RedirectResponse("/admin/news", 302)


@router.get("/news/{post_id}/edit", response_class=HTMLResponse)
async def news_edit_page(post_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    admin = await _require_admin(request, db)
    badges = await _badges(db)
    post = (await db.execute(select(NewsPost).where(NewsPost.id == post_id))).scalar_one_or_none()
    if not post:
        return RedirectResponse("/admin/news", 302)
    return render(request, "admin/news_form.html", {"user": admin, **badges, "post": post})


@router.post("/news/{post_id}/edit")
async def news_edit(post_id: int, request: Request, db: AsyncSession = Depends(get_db),
                    title: str = Form(...), body: str = Form(""), excerpt: str = Form(""),
                    is_blog: str = Form("0"), is_published: str = Form("0"), category: str = Form(""),
                    cover: UploadFile = File(None)):
    admin = await _require_admin(request, db)
    from core.config import MAX_IMAGE_SIZE
    post = (await db.execute(select(NewsPost).where(NewsPost.id == post_id))).scalar_one_or_none()
    if not post:
        return RedirectResponse("/admin/news", 302)
    post.title = title
    post.body = body
    post.excerpt = excerpt
    post.is_blog = is_blog == "1"
    post.is_published = is_published == "1"
    post.category = category
    post.updated_at = datetime.now(timezone.utc)
    if cover and cover.filename:
        post.cover = await save_image(cover, "news", MAX_IMAGE_SIZE)
    await db.commit()
    return RedirectResponse("/admin/news", 302)


@router.post("/news/{post_id}/delete")
async def news_delete(post_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    await _require_admin(request, db)
    post = (await db.execute(select(NewsPost).where(NewsPost.id == post_id))).scalar_one_or_none()
    if post:
        await db.delete(post)
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
    ticket = (await db.execute(
        select(SupportTicket).where(SupportTicket.id == ticket_id).options(selectinload(SupportTicket.user))
    )).scalar_one_or_none()
    if ticket:
        ticket.manager_reply = reply
        ticket.assigned_to   = admin.id
        ticket.status        = TicketStatus(status)
        ticket.replied_at    = datetime.now(timezone.utc)
        if status == "closed":
            ticket.closed_at = datetime.now(timezone.utc)
        await create_notification(db, ticket.user_id, NotifType.ticket,
                                  "Ответ на ваш тикет", reply[:100], "/support")
        # Email пользователю
        if ticket.user and ticket.user.email:
            mail.send_ticket_reply(ticket.user.email, ticket_id, ticket.subject, reply)
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

_LOGS_PAGE_SIZE = 50


@router.get("/logs", response_class=HTMLResponse)
async def logs(request: Request, db: AsyncSession = Depends(get_db),
               page: int = Query(1, ge=1)):
    admin = await _require_admin(request, db)
    badges = await _badges(db)
    total = (await db.execute(select(func.count()).select_from(ActivityLog))).scalar() or 0
    logs_list = (await db.execute(
        select(ActivityLog).options(selectinload(ActivityLog.user))
        .order_by(ActivityLog.created_at.desc())
        .limit(_LOGS_PAGE_SIZE).offset((page - 1) * _LOGS_PAGE_SIZE)
    )).scalars().all()
    total_pages = max(1, (total + _LOGS_PAGE_SIZE - 1) // _LOGS_PAGE_SIZE)
    return render(request, "admin/logs.html", {
        "user": admin, **badges, "logs": logs_list,
        "page": page, "total_pages": total_pages, "total": total,
    })


# ── Settings ───────────────────────────────────────────────────────────────────

@router.get("/settings", response_class=HTMLResponse)
async def settings(request: Request, db: AsyncSession = Depends(get_db)):
    admin = await _require_admin(request, db)
    badges = await _badges(db)
    current = await get_all_settings(db)
    return render(request, "admin/settings.html", {"user": admin, **badges, "settings": current})


@router.post("/settings/save")
async def settings_save(request: Request, db: AsyncSession = Depends(get_db)):
    admin = await _require_admin(request, db)
    form  = await request.form()
    for key in TOGGLE_KEYS:
        await set_setting(db, key, "1" if form.get(key) == "1" else "0")
    for key in TEXT_KEYS:
        val = form.get(key)
        if val is not None:
            await set_setting(db, key, val.strip())
    await log_activity(db, admin.id, "settings_saved", "platform")
    await db.commit()
    return RedirectResponse("/admin/settings?saved=1", 302)


@router.post("/settings/clear-cache")
async def clear_cache(request: Request, db: AsyncSession = Depends(get_db)):
    admin = await _require_admin(request, db)
    await log_activity(db, admin.id, "cache_cleared", "platform")
    await db.commit()
    return JSONResponse({"ok": True, "message": "Кеш очищен"})


# ── Email Broadcast ────────────────────────────────────────────────────────────

@router.get("/broadcast", response_class=HTMLResponse)
async def broadcast_page(request: Request, db: AsyncSession = Depends(get_db)):
    admin = await _require_admin(request, db)
    badges = await _badges(db)
    campaigns = (await db.execute(
        select(EmailCampaign).order_by(EmailCampaign.created_at.desc()).limit(30)
    )).scalars().all()
    # Новости/блог для выбора источника рассылки
    news_posts = (await db.execute(
        select(NewsPost).where(NewsPost.is_published == True)
        .order_by(NewsPost.created_at.desc()).limit(50)
    )).scalars().all()
    # Сколько пользователей согласились на рассылку по ролям
    from sqlalchemy import func
    consent_total = (await db.execute(
        select(func.count(User.id)).where(User.email_consent == True, User.is_banned == False)
    )).scalar() or 0
    consent_by_role = {}
    for role in UserRole:
        cnt = (await db.execute(
            select(func.count(User.id)).where(
                User.email_consent == True, User.is_banned == False, User.role == role
            )
        )).scalar() or 0
        consent_by_role[role.value] = cnt

    return render(request, "admin/broadcast.html", {
        "user": admin, **badges,
        "campaigns": campaigns,
        "news_posts": news_posts,
        "consent_total": consent_total,
        "consent_by_role": consent_by_role,
    })


@router.get("/broadcast/consent-count", response_class=JSONResponse)
async def broadcast_consent_count(request: Request, db: AsyncSession = Depends(get_db),
                                   target_role: str = "all"):
    """AJAX: количество получателей с согласием на рассылку."""
    await _require_admin(request, db)
    from sqlalchemy import func
    q = select(func.count(User.id)).where(User.email_consent == True, User.is_banned == False)
    if target_role != "all":
        try:
            q = q.where(User.role == UserRole(target_role))
        except ValueError:
            pass
    count = (await db.execute(q)).scalar() or 0
    return JSONResponse({"count": count})


@router.post("/broadcast/send")
async def broadcast_send(request: Request, db: AsyncSession = Depends(get_db)):
    admin = await _require_admin(request, db)
    form  = await request.form()
    subject      = form.get("subject", "").strip()
    body_html    = form.get("body_html", "").strip()
    target_role  = form.get("target_role", "all")
    news_post_id = form.get("news_post_id", "")

    if not subject or not body_html:
        return RedirectResponse("/admin/broadcast?error=empty", 302)

    # Если выбрана новость — используем её контент
    if news_post_id:
        post = (await db.execute(select(NewsPost).where(NewsPost.id == int(news_post_id)))).scalar_one_or_none()
        if post:
            if not subject:
                subject = post.title
            body_html = f"<h2>{post.title}</h2>{post.excerpt or ''}<hr>{post.body or ''}"

    campaign = EmailCampaign(
        author_id=admin.id, subject=subject, body=body_html,
        target_role=target_role, status="sending",
    )
    db.add(campaign)
    await db.flush()

    # Получаем ТОЛЬКО пользователей с согласием на рассылку
    q = select(User).where(User.email_consent == True, User.is_banned == False)
    if target_role != "all":
        try:
            q = q.where(User.role == UserRole(target_role))
        except ValueError:
            pass
    users = (await db.execute(q)).scalars().all()

    sent = 0
    for u in users:
        if u.email:
            mail.send_bulk_email(u.email, subject, body_html)
            sent += 1

    campaign.sent_count = sent
    campaign.status     = "done"
    campaign.sent_at    = datetime.now(timezone.utc)
    await log_activity(db, admin.id, "broadcast_sent",
                       detail=f"subject={subject[:60]}, sent={sent}, role={target_role}")
    await db.commit()
    return RedirectResponse("/admin/broadcast?sent=1", 302)


# ── Reports ────────────────────────────────────────────────────────────────────

async def _collect_report_data(db: AsyncSession) -> dict:
    """Собирает данные для отчётов."""
    from models.deal import Payment
    from sqlalchemy.orm import selectinload as sl

    # Пользователи по ролям
    users_total = (await db.execute(select(func.count(User.id)))).scalar() or 0
    users_by_role = {}
    for role in UserRole:
        cnt = (await db.execute(
            select(func.count(User.id)).where(User.role == role)
        )).scalar() or 0
        users_by_role[role.value] = cnt

    # Стартапы
    from models.startup import Startup
    from models.enums import StartupStatus
    startups_total = (await db.execute(select(func.count(Startup.id)))).scalar() or 0
    startups_active = (await db.execute(
        select(func.count(Startup.id)).where(Startup.status == StartupStatus.active)
    )).scalar() or 0
    startups_sold = (await db.execute(
        select(func.count(Startup.id)).where(Startup.status == StartupStatus.sold)
    )).scalar() or 0

    # Сделки
    deals_total = (await db.execute(select(func.count(Deal.id)))).scalar() or 0
    deals_by_status = {}
    for status in DealStatus:
        cnt = (await db.execute(
            select(func.count(Deal.id)).where(Deal.status == status)
        )).scalar() or 0
        deals_by_status[status.value] = cnt
    deals_amount_total = (await db.execute(
        select(func.sum(Deal.final_amount)).where(Deal.status == DealStatus.closed_ok)
    )).scalar() or 0

    # Транзакции / финансы
    deposits_total = (await db.execute(
        select(func.sum(Transaction.amount)).where(Transaction.type == "deposit")
    )).scalar() or 0
    deposits_count = (await db.execute(
        select(func.count(Transaction.id)).where(Transaction.type == "deposit")
    )).scalar() or 0

    # Последние сделки
    recent_deals = (await db.execute(
        select(Deal).options(
            sl(Deal.startup), sl(Deal.buyer)
        ).order_by(Deal.created_at.desc()).limit(20)
    )).scalars().all()

    # Топ стартапы по сделкам
    top_startups = (await db.execute(
        select(Startup).where(Startup.deals_count > 0)
        .order_by(Startup.deals_count.desc()).limit(10)
    )).scalars().all()

    return {
        "users_total": users_total,
        "users_by_role": users_by_role,
        "startups_total": startups_total,
        "startups_active": startups_active,
        "startups_sold": startups_sold,
        "deals_total": deals_total,
        "deals_by_status": deals_by_status,
        "deals_amount_total": deals_amount_total,
        "deposits_total": deposits_total,
        "deposits_count": deposits_count,
        "recent_deals": recent_deals,
        "top_startups": top_startups,
    }


@router.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request, db: AsyncSession = Depends(get_db)):
    admin = await _require_admin(request, db)
    badges = await _badges(db)
    data = await _collect_report_data(db)
    return render(request, "admin/reports.html", {
        "user": admin, **badges, **data,
        "generated_at": datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC"),
    })


@router.get("/reports/download")
async def reports_download(request: Request, db: AsyncSession = Depends(get_db),
                            report_type: str = "general"):
    from fastapi.responses import Response
    from services.reports_pdf import generate_general_pdf, generate_deals_pdf, generate_financial_pdf
    await _require_admin(request, db)
    data = await _collect_report_data(db)
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")

    if report_type == "deals":
        pdf_bytes = generate_deals_pdf(data)
        filename = f"starthub_deals_{date_str}.pdf"
    elif report_type == "financial":
        pdf_bytes = generate_financial_pdf(data)
        filename = f"starthub_financial_{date_str}.pdf"
    else:
        pdf_bytes = generate_general_pdf(data)
        filename = f"starthub_general_{date_str}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
