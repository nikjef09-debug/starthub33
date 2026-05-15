import os
import sys
from pathlib import Path

# === ФИКС ДЛЯ СБОРКИ В EXE ===
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

# === АВТОЗАГРУЗКА .env ===
# Загружаем .env автоматически — не нужно ничего настраивать вручную
try:
    from dotenv import load_dotenv
    _env_file = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(_env_file)
except ImportError:
    pass  # python-dotenv не установлен — читаем из системных переменных

# === ОПРЕДЕЛЕНИЕ ПУТЕЙ ===
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys._MEIPASS)
    EXE_DIR  = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent
    EXE_DIR  = BASE_DIR

STATIC_DIR    = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
UPLOAD_DIR    = STATIC_DIR / "uploads"

DB_PATH      = EXE_DIR / "starthub.db"
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

# === SECURITY ===
# В dev-режиме используется дефолтный ключ с предупреждением.
# В продакшне ОБЯЗАТЕЛЬНО задайте SECRET_KEY в .env
_DEFAULT_KEY = "starthub-dev-secret-key-change-in-production-32chars"
SECRET_KEY = os.getenv("SECRET_KEY", _DEFAULT_KEY)
if SECRET_KEY == _DEFAULT_KEY:
    print("\033[93m[WARNING] SECRET_KEY не задан — используется дефолтный ключ. "
          "Создайте .env файл перед деплоем!\033[0m")

ALGORITHM                = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30

MAX_IMAGE_SIZE = (1280, 720)
AVATAR_SIZE    = (256, 256)

# === EMAIL ===
EMAIL_USER = os.getenv("EMAIL_USER", "")
EMAIL_PASS = os.getenv("EMAIL_PASS", "")

if not EMAIL_USER or not EMAIL_PASS:
    print("\033[93m[WARNING] EMAIL_USER / EMAIL_PASS не заданы — отправка писем отключена.\033[0m")

APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")
