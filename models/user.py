from datetime import datetime, timezone
from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float,
    ForeignKey, Integer, String, Table, Text,
)
from sqlalchemy.orm import relationship

from core.database import Base
from models.enums import UserRole, WithdrawStatus


# ── Association tables ─────────────────────────────────────────────────────────

favorites = Table(
    "favorites", Base.metadata,
    Column("user_id",    ForeignKey("users.id"),    primary_key=True),
    Column("startup_id", ForeignKey("startups.id"), primary_key=True),
)


# ── User ───────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id              = Column(Integer, primary_key=True)
    email           = Column(String(255), unique=True, nullable=False, index=True)
    username        = Column(String(64),  unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role            = Column(Enum(UserRole), default=UserRole.buyer, nullable=False)
    full_name       = Column(String(128))
    avatar          = Column(String(512))
    bio             = Column(Text)
    phone           = Column(String(32))
    telegram        = Column(String(64))
    website         = Column(String(256))
    location        = Column(String(128))
    is_active       = Column(Boolean, default=True)
    is_verified     = Column(Boolean, default=False)
    is_banned       = Column(Boolean, default=False)
    ban_reason      = Column(Text)
    last_seen       = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    created_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                             onupdate=lambda: datetime.now(timezone.utc))

    startups          = relationship("Startup", back_populates="author", lazy="select")
    deals_as_buyer    = relationship("Deal", back_populates="buyer", foreign_keys="Deal.buyer_id")
    messages          = relationship("Message", back_populates="sender")
    favorite_startups = relationship("Startup", secondary=favorites, back_populates="favorited_by")
    notifications     = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
    reviews_given     = relationship("Review", back_populates="author",      foreign_keys="Review.author_id")
    reviews_received  = relationship("Review", back_populates="target_user", foreign_keys="Review.target_user_id")
    tickets           = relationship("SupportTicket", back_populates="user", foreign_keys="SupportTicket.user_id")
    wallet            = relationship("Wallet", back_populates="user", uselist=False, cascade="all, delete-orphan")
    activity_logs     = relationship("ActivityLog", back_populates="user", cascade="all, delete-orphan")


# ── Password reset token ───────────────────────────────────────────────────────

class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id         = Column(Integer, primary_key=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    token      = Column(String(128), unique=True, nullable=False, index=True)
    is_used    = Column(Boolean, default=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User")


# ── Wallet & Transactions ──────────────────────────────────────────────────────

class Wallet(Base):
    __tablename__ = "wallets"

    id              = Column(Integer, primary_key=True)
    user_id         = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    balance         = Column(Float, default=0.0)
    reserved        = Column(Float, default=0.0)
    total_deposited = Column(Float, default=0.0)
    total_withdrawn = Column(Float, default=0.0)
    updated_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                             onupdate=lambda: datetime.now(timezone.utc))

    user         = relationship("User", back_populates="wallet")
    transactions = relationship("Transaction", back_populates="wallet", cascade="all, delete-orphan")


class Transaction(Base):
    __tablename__ = "transactions"

    id          = Column(Integer, primary_key=True)
    wallet_id   = Column(Integer, ForeignKey("wallets.id"), nullable=False, index=True)
    deal_id     = Column(Integer, ForeignKey("deals.id"),   nullable=True)
    type        = Column(String(32))   # deposit / withdraw / fee / deal_payment
    amount      = Column(Float, nullable=False)
    status      = Column(Enum(WithdrawStatus), default=WithdrawStatus.pending)
    description = Column(String(512))
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    wallet = relationship("Wallet", back_populates="transactions")


# ── Activity log ───────────────────────────────────────────────────────────────

class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id         = Column(Integer, primary_key=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    action     = Column(String(128), nullable=False)
    entity     = Column(String(64))
    entity_id  = Column(Integer)
    detail     = Column(Text)
    ip         = Column(String(64))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="activity_logs")
