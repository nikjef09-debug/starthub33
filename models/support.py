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
    # ─── NEW: управление показом отзыва на главной странице (из админки) ───
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
