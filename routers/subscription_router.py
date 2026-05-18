"""
routers/subscription.py — покупка тарифов, управление подпиской
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.database import get_db
from core.security import get_current_user
from models.user import User, Wallet, Transaction
from models.subscription import Subscription, PLANS, get_plan
from models.enums import WithdrawStatus
from models.support import Notification
from models.enums import NotifType
from services.notifications import create_notification, log_activity
from routers.deps import render

router = APIRouter(prefix="/subscription", tags=["subscription"])


# ── Хелпер: получить или создать подписку ──────────────────────────────────────

async def get_or_create_subscription(user_id: int, db: AsyncSession) -> Subscription:
    sub = (await db.execute(
        select(Subscription).where(Subscription.user_id == user_id)
    )).scalar_one_or_none()
    if not sub:
        sub = Subscription(user_id=user_id, plan="free", is_active=True)
        db.add(sub)
        await db.flush()
    return sub


# ── Хелпер: проверить лимит стартапов ─────────────────────────────────────────

async def check_startup_limit(user: User, db: AsyncSession) -> tuple[bool, str]:
    from models.startup import Startup
    from sqlalchemy import func
    sub = await get_or_create_subscription(user.id, db)
    plan = sub.effective_plan
    count = (await db.execute(
        select(func.count()).where(Startup.author_id == user.id)
    )).scalar()
    if count >= plan["max_startups"]:
        return False, f"Ваш тариф «{plan['label']}» допускает максимум {plan['max_startups']} стартап(ов). Обновите план."
    return True, ""


async def check_deal_limit(user: User, db: AsyncSession) -> tuple[bool, str]:
    from models.deal import Deal
    from models.enums import DealStatus
    from sqlalchemy import func
    sub = await get_or_create_subscription(user.id, db)
    plan = sub.effective_plan
    count = (await db.execute(
        select(func.count()).where(
            Deal.buyer_id == user.id,
            Deal.status.in_([DealStatus.pending, DealStatus.active])
        )
    )).scalar()
    if count >= plan["max_deals"]:
        return False, f"Ваш тариф «{plan['label']}» допускает максимум {plan['max_deals']} активных сделок. Обновите план."
    return True, ""


async def check_document_limit(deal_id: int, db: AsyncSession) -> tuple[bool, str]:
    from models.deal import Deal, DealDocument
    from sqlalchemy import func
    sub_info = None
    deal = (await db.execute(select(Deal).where(Deal.id == deal_id))).scalar_one_or_none()
    if not deal:
        return True, ""
    sub = await get_or_create_subscription(deal.buyer_id, db)
    plan = sub.effective_plan
    count = (await db.execute(
        select(func.count()).where(DealDocument.deal_id == deal_id)
    )).scalar()
    if count >= plan["max_documents"]:
        return False, f"Лимит документов для вашего тарифа: {plan['max_documents']} шт."
    return True, ""


# ── Страница управления подпиской ──────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
async def subscription_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", 302)
    sub = await get_or_create_subscription(user.id, db)
    await db.commit()
    wallet = (await db.execute(select(Wallet).where(Wallet.user_id == user.id))).scalar_one_or_none()
    return render(request, "user/subscription.html", {
        "user": user,
        "sub": sub,
        "plans": PLANS,
        "wallet": wallet,
        "current_plan": sub.effective_plan,
    })


# ── Купить / сменить тариф ─────────────────────────────────────────────────────

@router.post("/buy")
async def buy_plan(
    request: Request,
    db: AsyncSession = Depends(get_db),
    plan_name: str = Form(...),
):
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", 302)

    plan = get_plan(plan_name)
    if plan_name not in PLANS:
        raise HTTPException(400, "Неизвестный тариф")

    price = plan["price"]

    # Получаем кошелёк
    wallet = (await db.execute(select(Wallet).where(Wallet.user_id == user.id))).scalar_one_or_none()
    if not wallet:
        return RedirectResponse("/subscription?error=no_wallet", 302)

    # Бесплатный план — просто переключаем
    if price == 0:
        sub = await get_or_create_subscription(user.id, db)
        sub.plan = "free"
        sub.is_active = True
        sub.expires_at = None
        sub.paid_amount = 0
        await log_activity(db, user.id, "plan_changed", "subscription", sub.id, detail="→ free")
        await db.commit()
        return RedirectResponse("/subscription?success=1", 302)

    # Проверяем баланс
    if wallet.balance < price:
        return RedirectResponse(f"/subscription?error=insufficient&need={price}&have={int(wallet.balance)}", 302)

    # Списываем
    wallet.balance -= price
    wallet.total_withdrawn += price

    # Создаём транзакцию
    db.add(Transaction(
        wallet_id=wallet.id,
        type="subscription",
        amount=-price,
        status=WithdrawStatus.approved,
        description=f"Подписка {plan['label']} на 30 дней",
    ))

    # Обновляем подписку
    sub = await get_or_create_subscription(user.id, db)
    sub.plan = plan_name
    sub.is_active = True
    sub.started_at = datetime.now(timezone.utc)
    sub.expires_at = datetime.now(timezone.utc) + timedelta(days=30)
    sub.paid_amount = price
    sub.auto_renew = True

    # Уведомление
    await create_notification(
        db, user.id, NotifType.system,
        f"Тариф {plan['label']} активирован",
        f"Подписка действует 30 дней до {sub.expires_at.strftime('%d.%m.%Y')}",
        "/subscription",
    )
    await log_activity(db, user.id, "plan_purchased", "subscription", sub.id, detail=f"→ {plan_name}, -{price}₽")
    await db.commit()
    return RedirectResponse("/subscription?success=1", 302)


# ── Отменить автопродление ─────────────────────────────────────────────────────

@router.post("/cancel")
async def cancel_subscription(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", 302)
    sub = await get_or_create_subscription(user.id, db)
    sub.auto_renew = False
    await log_activity(db, user.id, "plan_cancelled", "subscription", sub.id)
    await db.commit()
    return RedirectResponse("/subscription?cancelled=1", 302)
