"""
models/subscription.py — модели подписок и тарифных планов
"""
from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from core.database import Base


# ── Тарифные планы (статические, создаются при старте) ─────────────────────────

PLANS = {
    "free": {
        "name": "free",
        "label": "Free",
        "emoji": "🌱",
        "price": 0,
        "max_startups": 1,
        "max_deals": 3,
        "max_documents": 3,
        "priority_catalog": False,
        "manager_in_chat": False,
        "analytics": False,
        "white_label": False,
        "dedicated_manager": False,
        "api_access": False,
        "support_24_7": False,
        "description": "Для старта",
    },
    "starter": {
        "name": "starter",
        "label": "Starter",
        "emoji": "🌱",
        "price": 4990,
        "max_startups": 1,
        "max_deals": 3,
        "max_documents": 3,
        "priority_catalog": False,
        "manager_in_chat": False,
        "analytics": False,
        "white_label": False,
        "dedicated_manager": False,
        "api_access": False,
        "support_24_7": False,
        "description": "Для первых шагов",
    },
    "pro": {
        "name": "pro",
        "label": "Pro",
        "emoji": "🚀",
        "price": 14990,
        "max_startups": 5,
        "max_deals": 999,
        "max_documents": 50,
        "priority_catalog": True,
        "manager_in_chat": True,
        "analytics": True,
        "white_label": False,
        "dedicated_manager": False,
        "api_access": False,
        "support_24_7": False,
        "description": "Для активного роста",
    },
    "enterprise": {
        "name": "enterprise",
        "label": "Enterprise",
        "emoji": "⚡",
        "price": 39990,
        "max_startups": 999,
        "max_deals": 999,
        "max_documents": 999,
        "priority_catalog": True,
        "manager_in_chat": True,
        "analytics": True,
        "white_label": True,
        "dedicated_manager": True,
        "api_access": True,
        "support_24_7": True,
        "description": "Для масштаба",
    },
}


def get_plan(name: str) -> dict:
    return PLANS.get(name, PLANS["free"])


# ── Модель подписки пользователя ───────────────────────────────────────────────

class Subscription(Base):
    __tablename__ = "subscriptions"

    id          = Column(Integer, primary_key=True)
    user_id     = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    plan        = Column(String(32), default="free", nullable=False)   # free / starter / pro / enterprise
    is_active   = Column(Boolean, default=True)
    started_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at  = Column(DateTime, nullable=True)   # NULL = бессрочно (для теста), иначе +30 дней
    auto_renew  = Column(Boolean, default=True)
    paid_amount = Column(Float, default=0.0)
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                         onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="subscription")

    @property
    def plan_data(self) -> dict:
        return get_plan(self.plan)

    @property
    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        return datetime.now(timezone.utc) > self.expires_at.replace(tzinfo=timezone.utc)

    @property
    def effective_plan(self) -> dict:
        """Возвращает plan_data, но если подписка истекла — возвращает free."""
        if self.is_expired:
            return get_plan("free")
        return get_plan(self.plan)
