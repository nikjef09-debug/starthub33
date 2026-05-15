"""Shared dependencies and helpers for all routers."""
from fastapi import Request
from fastapi.responses import HTMLResponse


def render(request: Request, template_name: str, context: dict) -> HTMLResponse:
    """Render a Jinja2 template using the templates object stored in app.state."""
    context["request"] = request
    return request.app.state.templates.TemplateResponse(template_name, context)
