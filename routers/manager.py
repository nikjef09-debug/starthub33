from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.database import get_db
from core.security import get_current_user
from models.enums import DealStatus, StartupStatus, TicketStatus, UserRole
from models.deal import Deal
from models.startup import Startup
from models.support import SupportTicket
from models.user import User
from services.notifications import create_notification
from models.enums import NotifType
from routers.deps import render

router = APIRouter(prefix="/manager")


async def _require_manager(request: Request, db: AsyncSession) -> User:
    user = await get_current_user(request, db)
    if not user or user.role not in (UserRole.admin, UserRole.manager):
        raise HTTPException(403, "Доступ запрещён")
    return user





@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    user = await _require_manager(request, db)
    if user.role == UserRole.admin:
        return RedirectResponse("/admin/dashboard", 302)
    active_deals = (await db.execute(
        select(Deal).options(selectinload(Deal.startup), selectinload(Deal.buyer))
        .where(Deal.status.in_([DealStatus.pending, DealStatus.active, DealStatus.documents]))
        .order_by(Deal.created_at.desc()).limit(20)
    )).scalars().all()
    my_tickets = (await db.execute(
        select(SupportTicket).options(selectinload(SupportTicket.user))
        .where(or_(SupportTicket.assigned_to == user.id, SupportTicket.status == TicketStatus.open))
        .order_by(SupportTicket.created_at.desc()).limit(20)
    )).scalars().all()
    ticket_count = (await db.execute(select(func.count(SupportTicket.id)).where(SupportTicket.status == TicketStatus.open))).scalar()
    return render(request, "manager/dashboard.html", {
        "user": user, "active_deals": active_deals, "my_tickets": my_tickets,
        "deal_count": len(active_deals), "ticket_count": ticket_count,
    })


@router.get("/deals", response_class=HTMLResponse)
async def deals(request: Request, db: AsyncSession = Depends(get_db)):
    user = await _require_manager(request, db)
    if user.role == UserRole.admin:
        return RedirectResponse("/admin/deals", 302)
    deals_list = (await db.execute(
        select(Deal).options(selectinload(Deal.startup), selectinload(Deal.buyer))
        .order_by(Deal.created_at.desc())
    )).scalars().all()
    return render(request, "manager/deals.html", {"user": user, "deals": deals_list})


@router.get("/tickets", response_class=HTMLResponse)
async def tickets(request: Request, db: AsyncSession = Depends(get_db)):
    user = await _require_manager(request, db)
    if user.role == UserRole.admin:
        return RedirectResponse("/admin/tickets", 302)
    tickets_list = (await db.execute(
        select(SupportTicket).options(selectinload(SupportTicket.user))
        .order_by(SupportTicket.created_at.desc())
    )).scalars().all()
    return render(request, "manager/tickets.html", {"user": user, "tickets": tickets_list})


@router.post("/tickets/{ticket_id}/reply")
async def ticket_reply(ticket_id: int, request: Request, db: AsyncSession = Depends(get_db),
                       reply: str = Form(...), status: str = Form("in_progress")):
    user = await _require_manager(request, db)
    ticket = (await db.execute(select(SupportTicket).where(SupportTicket.id == ticket_id))).scalar_one_or_none()
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


@router.get("/startups", response_class=HTMLResponse)
async def startups(request: Request, db: AsyncSession = Depends(get_db)):
    user = await _require_manager(request, db)
    if user.role == UserRole.admin:
        return RedirectResponse("/admin/startups", 302)
    startups_list = (await db.execute(
        select(Startup).options(selectinload(Startup.author))
        .where(Startup.status == StartupStatus.active)
        .order_by(Startup.created_at.desc())
    )).scalars().all()
    return render(request, "manager/startups.html", {"user": user, "startups": startups_list})


@router.get("/users", response_class=HTMLResponse)
async def users(request: Request, db: AsyncSession = Depends(get_db)):
    user = await _require_manager(request, db)
    if user.role == UserRole.admin:
        return RedirectResponse("/admin/users", 302)
    users_list = (await db.execute(
        select(User).where(User.role.in_([UserRole.author, UserRole.buyer]))
        .order_by(User.created_at.desc())
    )).scalars().all()
    return render(request, "manager/users.html", {"user": user, "users": users_list})
