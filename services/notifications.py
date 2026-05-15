from sqlalchemy.ext.asyncio import AsyncSession

from models.enums import NotifType
from models.support import Notification
from models.user import ActivityLog


async def create_notification(
    db: AsyncSession,
    user_id: int,
    type: NotifType,
    title: str,
    body: str = "",
    link: str = "",
) -> None:
    notif = Notification(user_id=user_id, type=type, title=title, body=body, link=link)
    db.add(notif)


async def log_activity(
    db: AsyncSession,
    user_id: int,
    action: str,
    entity: str = "",
    entity_id: int = None,
    detail: str = "",
    ip: str = "",
) -> None:
    log = ActivityLog(
        user_id=user_id, action=action, entity=entity,
        entity_id=entity_id, detail=detail, ip=ip,
    )
    db.add(log)
