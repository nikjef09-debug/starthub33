import sys
import threading
import time
import webbrowser
import multiprocessing
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.config import STATIC_DIR, TEMPLATES_DIR
from core.database import init_db
from utils.helpers import fmt_money
from utils.seed import seed_db

# ── Lifespan ───────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    from core.database import async_session_maker
    async with async_session_maker() as db:
        await seed_db(db)
    yield


# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(title="StartHub v2", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.filters["money"] = fmt_money
app.state.templates = templates

# ── Routers ────────────────────────────────────────────────────────────────────

from routers import auth, public, user, deal, admin, manager  # noqa: E402

app.include_router(auth.router)
app.include_router(public.router)
app.include_router(user.router)
app.include_router(deal.router)
app.include_router(admin.router)
app.include_router(manager.router)

# ── Browser auto-open ──────────────────────────────────────────────────────────

def _open_browser():
    time.sleep(2)
    webbrowser.open("http://127.0.0.1:8000")


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    multiprocessing.freeze_support()
    threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
