# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the project

```bash
# Install dependencies
pip install -r requirements.txt

# Run (opens browser automatically)
python main.py

# Run migrations after adding new DB columns (uses aiosqlite directly)
python migrate.py
```

No test suite exists. No linter is configured.

## Environment variables (`.env` in project root)

| Variable | Required | Default |
|---|---|---|
| `SECRET_KEY` | Yes (for prod) | hardcoded dev key |
| `EMAIL_USER` | No | `""` (disables email) |
| `EMAIL_PASS` | No | `""` |
| `APP_BASE_URL` | No | `http://localhost:8000` |

Without `EMAIL_USER`/`EMAIL_PASS` the app starts fine — emails are silently skipped.

## Architecture overview

**SSR web app** — FastAPI renders Jinja2 templates server-side. There is no REST API / SPA frontend. Auth is JWT stored in an `access_token` **cookie** (not Authorization header).

### Database

SQLite via `aiosqlite` + SQLAlchemy 2.0 async. File: `starthub.db` in project root.

`init_db()` calls `Base.metadata.create_all` — it **only creates missing tables**, never alters existing columns. When adding columns, add a migration to `migrate.py` and run it once manually.

`models/__init__.py` imports every model so SQLAlchemy registers them before `create_all`.

### Startup sequence (`main.py` → `lifespan`)

```
init_db()          # create_all tables
seed_db(db)        # insert demo data (skipped if admin user already exists)
init_role_configs(db)  # upsert RoleConfig for 4 base roles
```

### Roles and permissions

Four system roles in `models/enums.UserRole`: `buyer`, `author`, `manager`, `admin`.

`User.role` is a SQLAlchemy `Enum(UserRole)` column — adding a 5th role requires changing the enum and a DB migration.

**`RoleConfig`** (table `role_configs`) — one row per base role, stores:
- `label`, `description` — display names
- `visible_at_registration` — controls whether the role appears in the `/register` dropdown
- `permissions` — JSON dict of 17 permission keys (see `models/support.PERM_KEYS`)

**`CustomRole`** (table `custom_roles`) — named permission presets assignable to specific users via `User.custom_role_name`. Supplements the base role, does not replace it.

**`get_effective_permissions(user, db)`** in `routers/deps.py` — merges RoleConfig + CustomRole into a final `dict[str, bool]`. Admin always gets all True. Used by `routers/manager.py` to gate every endpoint.

### Router → permission mapping (manager panel)

| Route | Required permission |
|---|---|
| `/manager/deals` | `view_deals` |
| `/manager/tickets` | `view_tickets` |
| `/manager/tickets/{id}/reply` | `reply_tickets` |
| `/manager/startups` | `view_startups` |
| `/manager/users` | `view_users` |

`/admin/*` is gated by `role == admin` only (no permission granularity).

### Key shared utilities

- **`routers/deps.py`** — `render()` (Jinja2 wrapper), `get_effective_permissions()`, `require_perm()`
- **`services/email.py`** — SMTP via `mail.ru` SSL port 465. All sends are fire-and-forget (`asyncio.create_task`). Credentials hardcoded in the file (`SMTP_USER`, `SMTP_PASS`).
- **`services/settings.py`** — `PlatformSetting` key-value store. `TOGGLE_KEYS` (0/1) and `TEXT_KEYS` (arbitrary string) define which settings exist. `get_all_settings()` merges DB values over `DEFAULTS`.
- **`services/websocket.py`** — in-memory `ConnectionManager` keyed by `deal_id`. Lost on server restart.
- **`utils/seed.py`** — `seed_db()` creates demo users/startups/deals; `init_role_configs()` idempotently upserts base role configs.

### Email broadcast consent

`User.email_consent` (Boolean, default False) — set via checkbox at registration. The `/admin/broadcast/send` endpoint **filters recipients to `email_consent=True` only**. Never send to all users ignoring this field.

### Template rendering

`routers/deps.render(request, template_name, context)` wraps `TemplateResponse`. Variables set inside `{% block admin_head %}` via `{% set %}` are **not available** in `{% block admin_content %}` due to Jinja2 block scoping — define shared variables at the top of the block that uses them.

### PyInstaller support

`core/config.py` checks `sys.frozen` and `sys._MEIPASS` to support `.exe` builds. `BASE_DIR` and `EXE_DIR` diverge in frozen mode — always use these constants for file paths, never hardcode.
