from datetime import datetime, timezone
from sqlalchemy import (
    Boolean, Column, DateTime, Enum,
    ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import relationship

from core.database import Base
from models.enums import (
    NotifType, ReviewTarget, TicketStatus, TicketPriority,
)

PERM_KEYS = [
    "view_users", "edit_users", "ban_users",
    "view_deals", "edit_deals", "close_deals",
    "view_startups", "edit_startups", "verify_startups",
    "view_tickets", "reply_tickets",
    "view_analytics", "view_logs",
    "send_broadcast", "manage_news",
    "manage_settings", "manage_roles",
]

PERM_LABELS: dict[str, str] = {
    "view_users":       "Просмотр пользователей",
    "edit_users":       "Редактирование пользователей",
    "ban_users":        "Блокировка пользователей",
    "view_deals":       "Просмотр сделок",
    "edit_deals":       "Редактирование сделок",
    "close_deals":      "Закрытие сделок",
    "view_startups":    "Просмотр стартапов",
    "edit_startups":    "Редактирование стартапов",
    "verify_startups":  "Верификация стартапов",
    "view_tickets":     "Просмотр тикетов",
    "reply_tickets":    "Ответ на тикеты",
    "view_analytics":   "Просмотр аналитики",
    "view_logs":        "Просмотр логов",
    "send_broadcast":   "Рассылка сообщений",
    "manage_news":      "Управление новостями",
    "manage_settings":  "Управление настройками",
    "manage_roles":     "Управление ролями",
}

DEFAULT_ROLE_CONFIGS = {
    "buyer": {
        "label": "Инвестор",
        "description": "Просматривает каталог и инициирует сделки",
        "visible_at_registration": True,
        "permissions": {},
    },
    "author": {
        "label": "Автор стартапа",
        "description": "Размещает стартапы и принимает предложения",
        "visible_at_registration": True,
        "permissions": {},
    },
    "manager": {
        "label": "Менеджер",
        "description": "Сопровождает сделки, работает с тикетами",
        "visible_at_registration": False,
        "permissions": {
            "view_users": True, "view_deals": True, "edit_deals": True,
            "close_deals": True, "view_startups": True,
            "view_tickets": True, "reply_tickets": True, "view_analytics": True,
        },
    },
    "admin": {
        "label": "Администратор",
        "description": "Полный доступ к платформе",
        "visible_at_registration": False,
        "permissions": {k: True for k in PERM_KEYS},
    },
    "developer": {
        "label": "Разработчик",
        "description": "Технический специалист платформы",
        "visible_at_registration": False,
        "permissions": {k: True for k in PERM_KEYS},
    },
}


# ── Notification ───────────────────────────────────────────────────────────────

class Notification(Base):
    __tablename__ = "notifications"

    id         = Column(Integer, primary_key=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    type       = Column(Enum(NotifType), default=NotifType.system)
    title      = Column(String(256), nullable=False)
    body       = Column(Text)
    link       = Column(String(512))
    is_read    = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="notifications")


# ── Review ─────────────────────────────────────────────────────────────────────

class Review(Base):
    __tablename__ = "reviews"

    id             = Column(Integer, primary_key=True)
    author_id      = Column(Integer, ForeignKey("users.id"),    nullable=False)
    target         = Column(Enum(ReviewTarget), nullable=False)
    startup_id     = Column(Integer, ForeignKey("startups.id"), nullable=True)
    target_user_id = Column(Integer, ForeignKey("users.id"),    nullable=True)
    deal_id        = Column(Integer, ForeignKey("deals.id"),     nullable=True)
    rating         = Column(Integer, nullable=False)   # 1-5
    comment        = Column(Text)
    is_visible     = Column(Boolean, default=True)
    is_featured_on_landing = Column(Boolean, default=False, nullable=False)
    created_at     = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    author      = relationship("User",    back_populates="reviews_given",    foreign_keys=[author_id])
    startup     = relationship("Startup", back_populates="reviews",          foreign_keys=[startup_id])
    target_user = relationship("User",    back_populates="reviews_received", foreign_keys=[target_user_id])


# ── Support Ticket ─────────────────────────────────────────────────────────────

class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id            = Column(Integer, primary_key=True)
    user_id       = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    assigned_to   = Column(Integer, ForeignKey("users.id"), nullable=True)
    subject       = Column(String(256), nullable=False)
    body          = Column(Text, nullable=False)
    status        = Column(Enum(TicketStatus),   default=TicketStatus.open)
    priority      = Column(Enum(TicketPriority), default=TicketPriority.medium)
    manager_reply = Column(Text)
    replied_at    = Column(DateTime, nullable=True)
    closed_at     = Column(DateTime, nullable=True)
    created_at    = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user     = relationship("User", back_populates="tickets",  foreign_keys=[user_id])
    assignee = relationship("User",                            foreign_keys=[assigned_to])


# ── News / Blog Post ───────────────────────────────────────────────────────────

class NewsPost(Base):
    __tablename__ = "news"

    id           = Column(Integer, primary_key=True)
    author_id    = Column(Integer, ForeignKey("users.id"), nullable=True)
    title        = Column(String(512), nullable=False)
    slug         = Column(String(512), unique=True, nullable=False)
    cover        = Column(String(512))
    excerpt      = Column(Text)
    body         = Column(Text)
    category     = Column(String(64))
    is_published = Column(Boolean, default=False)
    is_blog      = Column(Boolean, default=False)
    views_count  = Column(Integer, default=0)
    created_at   = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at   = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                          onupdate=lambda: datetime.now(timezone.utc))

    author = relationship("User")


# ── Platform Settings ──────────────────────────────────────────────────────────

class PlatformSetting(Base):
    """Хранит настройки платформы в виде key-value."""
    __tablename__ = "platform_settings"

    id    = Column(Integer, primary_key=True)
    key   = Column(String(128), unique=True, nullable=False, index=True)
    value = Column(String(1024), nullable=False, default="")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


# ── Role Config ─────────────────────────────────────────────────────────────────
# Конфигурация основных системных ролей: label, видимость при регистрации, права

class RoleConfig(Base):
    __tablename__ = "role_configs"

    id                      = Column(Integer, primary_key=True)
    role_name               = Column(String(32), unique=True, nullable=False, index=True)
    label                   = Column(String(128), nullable=False)
    description             = Column(String(256))
    visible_at_registration = Column(Boolean, default=True)
    permissions             = Column(Text, default="{}")  # JSON
    updated_at              = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                                     onupdate=lambda: datetime.now(timezone.utc))


# ── Custom Role ────────────────────────────────────────────────────────────────
# Дополнительные наборы прав, которые можно назначать пользователям поверх их основной роли

class CustomRole(Base):
    __tablename__ = "custom_roles"

    id          = Column(Integer, primary_key=True)
    name        = Column(String(64), unique=True, nullable=False)
    label       = Column(String(128), nullable=False)
    permissions = Column(Text, default="{}")
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ── Bulk Email Campaign ────────────────────────────────────────────────────────

class EmailCampaign(Base):
    """Массовые рассылки по всем пользователям."""
    __tablename__ = "email_campaigns"

    id           = Column(Integer, primary_key=True)
    author_id    = Column(Integer, ForeignKey("users.id"), nullable=True)
    subject      = Column(String(512), nullable=False)
    body         = Column(Text, nullable=False)
    target_role  = Column(String(64), default="all")  # all / buyer / author / manager
    sent_count   = Column(Integer, default=0)
    status       = Column(String(32), default="pending")  # pending / sending / done / failed
    created_at   = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    sent_at      = Column(DateTime, nullable=True)

    author = relationship("User")


# ── Email Verification Token ────────────────────────────────────────────────────

class EmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"

    id         = Column(Integer, primary_key=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    token      = Column(String(128), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User")
