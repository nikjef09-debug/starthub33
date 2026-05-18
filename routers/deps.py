"""Shared dependencies and helpers for all routers."""
import json

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.enums import UserRole
from models.support import PERM_KEYS, CustomRole, RoleConfig


def render(request: Request, template_name: str, context: dict) -> HTMLResponse:
    """Render a Jinja2 template using the templates object stored in app.state."""
    context.pop("request", None)
    return request.app.state.templates.TemplateResponse(
        request=request, name=template_name, context=context
    )


async def get_effective_permissions(user, db: AsyncSession) -> dict:
    """
    Возвращает итоговый словарь прав для пользователя.

    Порядок применения:
      1. Права из RoleConfig основной роли.
      2. Поверх — права из CustomRole (если назначен custom_role_name).
    Администратор всегда получает все права.
    """
    if user.role in (UserRole.admin, UserRole.developer):
        return {k: True for k in PERM_KEYS}

    perms: dict[str, bool] = {k: False for k in PERM_KEYS}

    # 1. Права основной роли
    role_config = (await db.execute(
        select(RoleConfig).where(RoleConfig.role_name == user.role.value)
    )).scalar_one_or_none()
    if role_config:
        try:
            for k, v in json.loads(role_config.permissions).items():
                if k in perms and v:
                    perms[k] = True
        except Exception:
            pass

    # 2. Дополнительные права из CustomRole
    if user.custom_role_name:
        custom_role = (await db.execute(
            select(CustomRole).where(CustomRole.name == user.custom_role_name)
        )).scalar_one_or_none()
        if custom_role:
            try:
                for k, v in json.loads(custom_role.permissions).items():
                    if k in perms and v:
                        perms[k] = True
            except Exception:
                pass

    return perms


def require_perm(perms: dict, key: str, detail: str | None = None) -> None:
    """Бросает 403 если у пользователя нет нужного права."""
    if not perms.get(key, False):
        raise HTTPException(403, detail or f"Нет доступа: требуется право «{key}»")
