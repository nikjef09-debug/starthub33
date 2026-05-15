from datetime import datetime, timezone
from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float,
    ForeignKey, Integer, String, Table, Text,
)
from sqlalchemy.orm import relationship

from core.database import Base
from models.enums import StartupStatus

# ── Association tables ─────────────────────────────────────────────────────────

startup_tags_assoc = Table(
    "startup_tags_assoc", Base.metadata,
    Column("startup_id", ForeignKey("startups.id"), primary_key=True),
    Column("tag_id",     ForeignKey("tags.id"),     primary_key=True),
)


# ── Tag ────────────────────────────────────────────────────────────────────────

class Tag(Base):
    __tablename__ = "tags"

    id       = Column(Integer, primary_key=True)
    name     = Column(String(64), unique=True, nullable=False)
    slug     = Column(String(64), unique=True, nullable=False)
    color    = Column(String(16), default="#E85D26")

    startups = relationship("Startup", secondary=startup_tags_assoc, back_populates="tags")


# ── Startup ────────────────────────────────────────────────────────────────────

class Startup(Base):
    __tablename__ = "startups"

    id            = Column(Integer, primary_key=True)
    author_id     = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title         = Column(String(256), nullable=False)
    slug          = Column(String(256), unique=True, nullable=False, index=True)
    category      = Column(String(64))
    stage         = Column(String(64))
    tagline       = Column(String(512))
    description   = Column(Text)
    cover_image   = Column(String(512))
    emoji         = Column(String(8), default="🚀")
    price         = Column(Float)
    revenue       = Column(Float)
    valuation     = Column(Float)
    team_size     = Column(Integer)
    founded_year  = Column(Integer)
    website       = Column(String(256))
    pitch_deck_url = Column(String(512))
    status        = Column(Enum(StartupStatus), default=StartupStatus.draft)
    is_featured   = Column(Boolean, default=False)
    is_verified   = Column(Boolean, default=False)
    views_count   = Column(Integer, default=0)
    deals_count   = Column(Integer, default=0)
    created_at    = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at    = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    author       = relationship("User", back_populates="startups")
    deals        = relationship("Deal", back_populates="startup")
    favorited_by = relationship("User", secondary="favorites", back_populates="favorite_startups")
    tags         = relationship("Tag",  secondary=startup_tags_assoc, back_populates="startups")
    reviews      = relationship("Review", back_populates="startup", foreign_keys="Review.startup_id")
