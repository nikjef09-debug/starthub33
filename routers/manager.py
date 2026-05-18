from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.database import get_db
from core.security import get_current_user
from models.enums import DealStatus, NotifType, StartupStatus, TicketStatus, UserRole
from models.deal import Deal
from models.startup import Startup
from models.support import SupportTicket
from models.user import User, Transaction
from services.notifications import create_notification
from routers.deps import render, get_effective_permissions, require_perm

router = APIRouter(prefix="/manager")

# Соответствие роут → требуемое право
ROUTE_PERMS: dict[str, str] = {
    "deals":    "view_deals",
    "tickets":  "view_tickets",
    "reply":    "reply_tickets",
    "startups": "view_startups",
    "users":    "view_users",
}


async def _require_manager(request: Request, db: AsyncSession) -> tuple[User, dict]:
    """
    Пропускает admin, manager, а также любого пользователя у которого есть
    хотя бы одно активное право (через custom_role_name или RoleConfig).
    """
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(403, "Необходима авторизация")
    perms = await get_effective_permissions(user, db)
    is_staff = user.role in (UserRole.admin, UserRole.manager)
    has_any_perm = any(perms.values())
    if not is_staff and not has_any_perm:
        raise HTTPException(403, "Нет доступа к панели управления")
    return user, perms


async def _mgr_ctx(user, perms, db: AsyncSession) -> dict:
    """Базовый контекст для всех manager-шаблонов (нужен sidebar)."""
    ticket_count = 0
    if perms.get("view_tickets"):
        ticket_count = (await db.execute(
            select(func.count(SupportTicket.id)).where(SupportTicket.status == TicketStatus.open)
        )).scalar() or 0
    return {"user": user, "perms": perms, "ticket_count": ticket_count}


# ── Dashboard ──────────────────────────────────────────────────────────────────

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    user, perms = await _require_manager(request, db)
    if user.role in (UserRole.admin, UserRole.developer):
        return RedirectResponse("/admin/dashboard", 302)

    active_deals = []
    my_tickets   = []
    ticket_count = 0

    if perms.get("view_deals"):
        active_deals = (await db.execute(
            select(Deal).options(selectinload(Deal.startup), selectinload(Deal.buyer))
            .where(Deal.status.in_([DealStatus.pending, DealStatus.active, DealStatus.documents]))
            .order_by(Deal.created_at.desc()).limit(20)
        )).scalars().all()

    if perms.get("view_tickets"):
        my_tickets = (await db.execute(
            select(SupportTicket).options(selectinload(SupportTicket.user))
            .where(or_(SupportTicket.assigned_to == user.id, SupportTicket.status == TicketStatus.open))
            .order_by(SupportTicket.created_at.desc()).limit(20)
        )).scalars().all()
        ticket_count = (await db.execute(
            select(func.count(SupportTicket.id)).where(SupportTicket.status == TicketStatus.open)
        )).scalar() or 0

    ctx = await _mgr_ctx(user, perms, db)
    return render(request, "manager/dashboard.html", {
        **ctx,
        "active_deals": active_deals, "my_tickets": my_tickets,
        "deal_count": len(active_deals),
    })


# ── Deals ──────────────────────────────────────────────────────────────────────

@router.get("/deals", response_class=HTMLResponse)
async def deals(request: Request, db: AsyncSession = Depends(get_db)):
    user, perms = await _require_manager(request, db)
    if user.role == UserRole.admin:
        return RedirectResponse("/admin/deals", 302)
    require_perm(perms, "view_deals", "Нет доступа к разделу «Сделки»")

    deals_list = (await db.execute(
        select(Deal).options(selectinload(Deal.startup), selectinload(Deal.buyer))
        .order_by(Deal.created_at.desc())
    )).scalars().all()
    ctx = await _mgr_ctx(user, perms, db)
    return render(request, "manager/deals.html", {**ctx, "deals": deals_list})


# ── Tickets ────────────────────────────────────────────────────────────────────

@router.get("/tickets", response_class=HTMLResponse)
async def tickets(request: Request, db: AsyncSession = Depends(get_db)):
    user, perms = await _require_manager(request, db)
    if user.role == UserRole.admin:
        return RedirectResponse("/admin/tickets", 302)
    require_perm(perms, "view_tickets", "Нет доступа к разделу «Тикеты»")

    tickets_list = (await db.execute(
        select(SupportTicket).options(selectinload(SupportTicket.user))
        .order_by(SupportTicket.created_at.desc())
    )).scalars().all()
    ctx = await _mgr_ctx(user, perms, db)
    return render(request, "manager/tickets.html", {**ctx, "tickets": tickets_list})


@router.post("/tickets/{ticket_id}/reply")
async def ticket_reply(ticket_id: int, request: Request, db: AsyncSession = Depends(get_db),
                       reply: str = Form(...), status: str = Form("in_progress")):
    user, perms = await _require_manager(request, db)
    require_perm(perms, "reply_tickets", "Нет права отвечать на тикеты")

    ticket = (await db.execute(
        select(SupportTicket).where(SupportTicket.id == ticket_id)
    )).scalar_one_or_none()
    if ticket:
        ticket.manager_reply = reply
        ticket.assigned_to   = user.id
        ticket.status        = TicketStatus(status)
        ticket.replied_at    = datetime.now(timezone.utc)
        if status == "closed":
            ticket.closed_at = datetime.now(timezone.utc)
        await create_notification(db, ticket.user_id, NotifType.system,
                                  "Ответ на ваш тикет", reply[:100], "/support")
        await db.commit()
    return RedirectResponse("/manager/tickets", 302)


# ── Startups ───────────────────────────────────────────────────────────────────

@router.get("/startups", response_class=HTMLResponse)
async def startups(request: Request, db: AsyncSession = Depends(get_db)):
    user, perms = await _require_manager(request, db)
    if user.role == UserRole.admin:
        return RedirectResponse("/admin/startups", 302)
    require_perm(perms, "view_startups", "Нет доступа к разделу «Стартапы»")

    startups_list = (await db.execute(
        select(Startup).options(selectinload(Startup.author))
        .where(Startup.status == StartupStatus.active)
        .order_by(Startup.created_at.desc())
    )).scalars().all()
    ctx = await _mgr_ctx(user, perms, db)
    return render(request, "manager/startups.html", {**ctx, "startups": startups_list})


# ── Users ──────────────────────────────────────────────────────────────────────

@router.get("/users", response_class=HTMLResponse)
async def users(request: Request, db: AsyncSession = Depends(get_db)):
    user, perms = await _require_manager(request, db)
    if user.role == UserRole.admin:
        return RedirectResponse("/admin/users", 302)
    require_perm(perms, "view_users", "Нет доступа к разделу «Пользователи»")

    users_list = (await db.execute(
        select(User).where(User.role.in_([UserRole.author, UserRole.buyer]))
        .order_by(User.created_at.desc())
    )).scalars().all()
    ctx = await _mgr_ctx(user, perms, db)
    return render(request, "manager/users.html", {**ctx, "users": users_list})


# ── Reports ────────────────────────────────────────────────────────────────────

@router.get("/reports", response_class=HTMLResponse)
async def reports(request: Request, db: AsyncSession = Depends(get_db)):
    user, perms = await _require_manager(request, db)
    if user.role in (UserRole.admin, UserRole.developer):
        return RedirectResponse("/admin/reports", 302)
    require_perm(perms, "view_analytics", "Нет доступа к отчётам")

    from routers.admin import _collect_report_data
    from datetime import datetime, timezone
    data = await _collect_report_data(db)
    ctx = await _mgr_ctx(user, perms, db)
    return render(request, "manager/reports.html", {
        **ctx, **data,
        "generated_at": datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC"),
    })


@router.get("/reports/download")
async def reports_download(request: Request, db: AsyncSession = Depends(get_db),
                            report_type: str = "general"):
    from fastapi.responses import Response, RedirectResponse as RR
    from services.reports_pdf import generate_general_pdf, generate_deals_pdf, generate_financial_pdf
    from datetime import datetime, timezone
    user, perms = await _require_manager(request, db)
    if user.role in (UserRole.admin, UserRole.developer):
        return RR(f"/admin/reports/download?report_type={report_type}", 302)
    require_perm(perms, "view_analytics")
    from routers.admin import _collect_report_data
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
