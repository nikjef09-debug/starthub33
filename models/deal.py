from datetime import datetime, timezone
from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float,
    ForeignKey, Integer, String, Table, Text,
)
from sqlalchemy.orm import relationship

from core.database import Base
from models.enums import DealStatus, MessageKind, PaymentMethod, PaymentStatus

# ── Association table ──────────────────────────────────────────────────────────

deal_managers = Table(
    "deal_managers", Base.metadata,
    Column("deal_id", ForeignKey("deals.id"), primary_key=True),
    Column("user_id", ForeignKey("users.id"), primary_key=True),
)


# ── Deal ───────────────────────────────────────────────────────────────────────

class Deal(Base):
    __tablename__ = "deals"

    id            = Column(Integer, primary_key=True)
    startup_id    = Column(Integer, ForeignKey("startups.id"), nullable=False, index=True)
    buyer_id      = Column(Integer, ForeignKey("users.id"),    nullable=False, index=True)
    status        = Column(Enum(DealStatus), default=DealStatus.pending)
    amount        = Column(Float)
    final_amount  = Column(Float)
    note          = Column(Text)
    reject_reason = Column(Text)
    # Тип оплаты
    payment_method = Column(Enum(PaymentMethod), nullable=True)
    payment_status = Column(Enum(PaymentStatus), default=PaymentStatus.pending)
    payment_note   = Column(Text)          # для наличных — заметка об оплате
    receipt_path   = Column(String(512))   # путь к чеку
    created_at    = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at    = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))
    closed_at     = Column(DateTime, nullable=True)

    startup   = relationship("Startup",       back_populates="deals")
    buyer     = relationship("User",          back_populates="deals_as_buyer", foreign_keys=[buyer_id])
    managers  = relationship("User",          secondary=deal_managers)
    messages  = relationship("Message",       back_populates="deal",  cascade="all, delete-orphan")
    documents = relationship("DealDocument",  back_populates="deal",  cascade="all, delete-orphan")
    payments  = relationship("Payment",       back_populates="deal",  cascade="all, delete-orphan")


# ── Message ────────────────────────────────────────────────────────────────────

class Message(Base):
    __tablename__ = "messages"

    id         = Column(Integer, primary_key=True)
    deal_id    = Column(Integer, ForeignKey("deals.id"),  nullable=False, index=True)
    sender_id  = Column(Integer, ForeignKey("users.id"),  nullable=True)
    type       = Column(Enum(MessageKind), default=MessageKind.text)
    body       = Column(Text, nullable=False)
    is_read    = Column(Boolean, default=False)
    edited_at  = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    deal   = relationship("Deal", back_populates="messages")
    sender = relationship("User", back_populates="messages")


# ── Deal Document ──────────────────────────────────────────────────────────────

class DealDocument(Base):
    __tablename__ = "deal_documents"

    id          = Column(Integer, primary_key=True)
    deal_id     = Column(Integer, ForeignKey("deals.id"),  nullable=False, index=True)
    uploader_id = Column(Integer, ForeignKey("users.id"),  nullable=False)
    filename    = Column(String(256))
    filepath    = Column(String(512))
    file_size   = Column(Integer)
    mime_type   = Column(String(128))
    doc_type    = Column(String(64), default="other")   # contract / receipt / completion / other
    is_signed   = Column(Boolean, default=False)
    signed_at   = Column(DateTime, nullable=True)
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    deal     = relationship("Deal", back_populates="documents")
    uploader = relationship("User")


# ── Payment ────────────────────────────────────────────────────────────────────

class Payment(Base):
    """Запись об оплате по сделке (онлайн / QR / наличные)."""
    __tablename__ = "payments"

    id             = Column(Integer, primary_key=True)
    deal_id        = Column(Integer, ForeignKey("deals.id"),  nullable=False, index=True)
    payer_id       = Column(Integer, ForeignKey("users.id"),  nullable=False)
    method         = Column(Enum(PaymentMethod), nullable=False)
    amount         = Column(Float, nullable=False)
    status         = Column(Enum(PaymentStatus), default=PaymentStatus.pending)
    note           = Column(Text)               # для наличных: описание
    receipt_path   = Column(String(512))        # путь к чеку/квитанции
    confirmed_by   = Column(Integer, ForeignKey("users.id"), nullable=True)
    confirmed_at   = Column(DateTime, nullable=True)
    created_at     = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    deal      = relationship("Deal", back_populates="payments")
    payer     = relationship("User", foreign_keys=[payer_id])
    confirmer = relationship("User", foreign_keys=[confirmed_by])
