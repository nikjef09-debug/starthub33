"""Сервис работы с настройками платформы (PlatformSetting)."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.support import PlatformSetting

# Ключи, которые являются переключателями (0 / 1)
TOGGLE_KEYS = {
    "registration_open",
    "require_email_confirm",
    "maintenance_mode",
    "moderation_before_pub",
    "auto_verify_domain",
    "email_new_deals",
    "push_messages",
    "weekly_digest",
    "rate_limiting",
    "log_all_actions",
}

# Ключи, которые хранят произвольный текст / число
TEXT_KEYS = {
    "platform_name",
    "platform_tagline",
    "contact_email",
    "commission_percent",
    "min_deal_amount",
    "max_deal_amount",
    "support_hours",
}

DEFAULTS: dict[str, str] = {
    # toggles
    "registration_open":     "1",
    "require_email_confirm": "0",
    "maintenance_mode":      "0",
    "moderation_before_pub": "0",
    "auto_verify_domain":    "1",
    "email_new_deals":       "1",
    "push_messages":         "1",
    "weekly_digest":         "0",
    "rate_limiting":         "1",
    "log_all_actions":       "1",
    # text
    "platform_name":         "StartHub",
    "platform_tagline":      "Маркетплейс стартапов",
    "contact_email":         "info@starthub.ru",
    "commission_percent":    "5",
    "min_deal_amount":       "0",
    "max_deal_amount":       "0",
    "support_hours":         "Пн–Пт, 10:00–19:00",
}


async def get_setting(db: AsyncSession, key: str) -> str:
    row = (await db.execute(
        select(PlatformSetting).where(PlatformSetting.key == key)
    )).scalar_one_or_none()
    return row.value if row else DEFAULTS.get(key, "")


async def set_setting(db: AsyncSession, key: str, value: str) -> None:
    row = (await db.execute(
        select(PlatformSetting).where(PlatformSetting.key == key)
    )).scalar_one_or_none()
    if row:
        row.value = value
    else:
        db.add(PlatformSetting(key=key, value=value))


async def get_all_settings(db: AsyncSession) -> dict:
    rows = (await db.execute(select(PlatformSetting))).scalars().all()
    result = dict(DEFAULTS)
    for row in rows:
        result[row.key] = row.value
    return result


async def is_maintenance(db: AsyncSession) -> bool:
    return (await get_setting(db, "maintenance_mode")) == "1"
