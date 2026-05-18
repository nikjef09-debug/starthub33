import sys
import logging
import threading
import time
import webbrowser
import multiprocessing
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.config import STATIC_DIR, TEMPLATES_DIR, APP_BASE_URL, CONTACT_EMAIL
from core.database import init_db
from utils.helpers import fmt_money
from utils.seed import seed_db, init_role_configs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# ── Lifespan ───────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    from core.database import async_session_maker
    async with async_session_maker() as db:
        await seed_db(db)
        await init_role_configs(db)
    yield


# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(title="StartHub v2", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        APP_BASE_URL,
        "https://starthub33.ru",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.filters["money"] = fmt_money
templates.env.filters["format_number"] = lambda n: f"{int(n):,}".replace(",", " ")
templates.env.globals["contact_email"] = CONTACT_EMAIL
app.state.templates = templates

# ── Routers ────────────────────────────────────────────────────────────────────

from routers import auth, public, user, deal, admin, manager  # noqa: E402
from routers import subscription  # noqa: E402

app.include_router(auth.router)
app.include_router(public.router)
app.include_router(user.router)
app.include_router(deal.router)
app.include_router(admin.router)
app.include_router(manager.router)
app.include_router(subscription.router)

# ── Browser auto-open (только локально) ───────────────────────────────────────

def _open_browser():
    time.sleep(2)
    webbrowser.open("http://127.0.0.1:8000")


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    multiprocessing.freeze_support()
    # Открываем браузер только на десктопе (не на VPS/headless)
    if sys.platform != "linux" or sys.stdout.isatty():
        threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run(
        app,
        host="0.0.0.0",   # слушаем все интерфейсы (нужно для VPS)
        port=8000,
        log_level="info",
    )
