import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from jose import jwt, JWTError

from core.config import SECRET_KEY, ALGORITHM, UPLOAD_DIR
from core.database import get_db
from core.security import get_current_user
from models.enums import DealStatus, MessageKind, NotifType, UserRole
from models.deal import Deal, Message, DealDocument
from models.startup import Startup
from models.user import User
from services.notifications import create_notification, log_activity
from services.websocket import ws_manager
from utils.helpers import fmt_money
from routers.deps import render

router = APIRouter()




# ── Create deal ────────────────────────────────────────────────────────────────

@router.post("/deal/create/{startup_id}")
async def create_deal(startup_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", 302)
    startup = (await db.execute(select(Startup).where(Startup.id == startup_id))).scalar_one_or_none()
    if not startup:
        raise HTTPException(404)
    existing = (await db.execute(
        select(Deal).where(
            Deal.startup_id == startup_id, Deal.buyer_id == user.id,
            Deal.status.in_([DealStatus.pending, DealStatus.active]),
        )
    )).scalar_one_or_none()
    if existing:
        return RedirectResponse(f"/deal/{existing.id}", 302)
    form = await request.form()
    deal = Deal(startup_id=startup_id, buyer_id=user.id, status=DealStatus.pending,
                amount=float(form.get("amount", 0) or 0) or None, note=form.get("note", ""))
    db.add(deal)
    await db.flush()
    startup.deals_count = (startup.deals_count or 0) + 1
    db.add(Message(deal_id=deal.id, sender_id=None, type=MessageKind.system,
                   body=f"Сделка создана. Покупатель: {user.full_name or user.username}. Ожидаем подтверждения."))
    await create_notification(
        db, startup.author_id, NotifType.deal_new,
        f"Новая сделка по «{startup.title}»",
        f"{user.full_name or user.username} предлагает {fmt_money(deal.amount) if deal.amount else 'сумму к обсуждению'}",
        link=f"/deal/{deal.id}",
    )
    await log_activity(db, user.id, "deal_created", "deal", deal.id, detail=startup.title)
    await db.commit()
    return RedirectResponse(f"/deal/{deal.id}", 302)


# ── Deal chat page ─────────────────────────────────────────────────────────────

@router.get("/deal/{deal_id}", response_class=HTMLResponse)
async def deal_chat(deal_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", 302)
    deal = (await db.execute(
        select(Deal).where(Deal.id == deal_id)
        .options(
            selectinload(Deal.startup).selectinload(Startup.author),
            selectinload(Deal.buyer),
            selectinload(Deal.managers),
            selectinload(Deal.messages).selectinload(Message.sender),
            selectinload(Deal.documents).selectinload(DealDocument.uploader),
        )
    )).scalar_one_or_none()
    if not deal:
        raise HTTPException(404)
    is_author  = deal.startup.author_id == user.id
    is_buyer   = deal.buyer_id == user.id
    is_manager = user.role in (UserRole.manager, UserRole.admin)
    if not (is_author or is_buyer or is_manager):
        raise HTTPException(403)
    return render(request, "deal/chat.html", {
        "user": user, "deal": deal,
        "is_author": is_author, "is_buyer": is_buyer, "is_manager": is_manager,
    })


# ── Change deal status ─────────────────────────────────────────────────────────

@router.post("/deal/{deal_id}/status")
async def update_deal_status(deal_id: int, request: Request, db: AsyncSession = Depends(get_db),
                              new_status: str = Form(...)):
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(401)
    deal = (await db.execute(
        select(Deal).options(selectinload(Deal.startup)).where(Deal.id == deal_id)
    )).scalar_one_or_none()
    if not deal:
        raise HTTPException(404)
    is_author  = deal.startup.author_id == user.id
    is_manager = user.role in (UserRole.manager, UserRole.admin)
    if not (is_author or is_manager):
        raise HTTPException(403)
    deal.status = DealStatus(new_status)
    if new_status in ("closed_ok", "closed_fail"):
        deal.closed_at = datetime.now(timezone.utc)
    db.add(Message(deal_id=deal_id, sender_id=user.id, type=MessageKind.system,
                   body=f"Статус изменён пользователем {user.full_name or user.username}."))
    await create_notification(db, deal.buyer_id, NotifType.deal_status,
                              "Статус сделки изменён", f"Новый статус: {new_status}", f"/deal/{deal_id}")
    await log_activity(db, user.id, "deal_status_changed", "deal", deal_id, detail=new_status)
    await db.commit()
    return RedirectResponse(f"/deal/{deal_id}", 302)


# ── Upload document ────────────────────────────────────────────────────────────

@router.post("/deal/{deal_id}/upload-doc")
async def upload_document(deal_id: int, request: Request,
                          db: AsyncSession = Depends(get_db),
                          file: UploadFile = File(...)):
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(401)
    deal = (await db.execute(
        select(Deal).options(selectinload(Deal.startup)).where(Deal.id == deal_id)
    )).scalar_one_or_none()
    if not deal:
        raise HTTPException(404)
    if not file.filename:
        raise HTTPException(400, "Файл не выбран")
    ext = Path(file.filename).suffix.lower()
    if ext not in {".pdf", ".doc", ".docx", ".png", ".jpg", ".jpeg"}:
        raise HTTPException(400, "Недопустимый тип файла")
    contents = await file.read()
    if not contents:
        raise HTTPException(400, "Пустой файл")
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(400, "Файл слишком большой (макс. 10 МБ)")

    upload_dir = UPLOAD_DIR / "docs"
    upload_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{ext}"
    (upload_dir / filename).write_bytes(contents)

    db.add(DealDocument(deal_id=deal_id, uploader_id=user.id,
                        filename=file.filename, filepath=f"/static/uploads/docs/{filename}",
                        file_size=len(contents), mime_type=file.content_type))
    db.add(Message(deal_id=deal_id, sender_id=user.id, type=MessageKind.document,
                   body=f"Загружен документ: {file.filename}"))
    await db.commit()

    await ws_manager.broadcast(deal_id, {
        "type": "document", "sender": user.full_name or user.username,
        "body": f"📎 Загружен документ: {file.filename}",
        "time": datetime.now(timezone.utc).strftime("%H:%M"),
    })
    return RedirectResponse(f"/deal/{deal_id}", 302)


# ── WebSocket ──────────────────────────────────────────────────────────────────

@router.websocket("/ws/deal/{deal_id}")
async def deal_websocket(deal_id: int, ws: WebSocket):
    from core.database import async_session_maker
    async with async_session_maker() as db:
        token = ws.query_params.get("token")
        user = None
        if token:
            try:
                payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
                user_id = payload.get("sub")
                result = await db.execute(select(User).where(User.id == int(user_id)))
                user = result.scalar_one_or_none()
            except Exception:
                pass
        if not user:
            await ws.close(code=1008)
            return
    await ws_manager.connect(deal_id, ws)
    try:
        while True:
            body = (await ws.receive_text()).strip()
            if not body:
                continue
            async with async_session_maker() as db:
                db.add(Message(deal_id=deal_id, sender_id=user.id, type=MessageKind.text, body=body))
                await db.commit()
            await ws_manager.broadcast(deal_id, {
                "type": "message", "sender_id": user.id,
                "sender": user.full_name or user.username,
                "body": body, "time": datetime.now(timezone.utc).strftime("%H:%M"),
            })
    except WebSocketDisconnect:
        ws_manager.disconnect(deal_id, ws)
