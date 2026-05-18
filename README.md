<<<<<<< HEAD
# StartHub v2 — Рефакторинг

## Структура проекта

```
starthub/
├── core/
│   ├── config.py       # конфиг, пути, переменные окружения
│   ├── database.py     # engine, сессии, Base
│   └── security.py     # JWT, хэширование паролей
├── models/
│   ├── enums.py        # все перечисления
│   ├── user.py         # User, Wallet, Transaction, ActivityLog
│   ├── startup.py      # Startup, Tag
│   ├── deal.py         # Deal, Message, DealDocument
│   └── support.py      # Notification, Review, SupportTicket, NewsPost
├── routers/
│   ├── auth.py         # /login, /register, /forgot-password, /reset-password
│   ├── public.py       # /, /catalog, /startup/{slug}, /news, /blog...
│   ├── user.py         # /profile, /wallet, /my-startups, /favorites...
│   ├── deal.py         # /deal/{id}, WebSocket, загрузка документов
│   ├── admin.py        # /admin/*
│   └── manager.py      # /manager/*
├── services/
│   ├── email.py        # отправка писем
│   ├── notifications.py # create_notification, log_activity
│   └── websocket.py    # ConnectionManager
├── utils/
│   ├── helpers.py      # slugify, fmt_money, save_image
│   └── seed.py         # начальные данные
├── templates/          # Jinja2 шаблоны (без изменений)
├── static/             # CSS, JS, загрузки (без изменений)
├── main.py             # точка входа (~40 строк)
├── .env.example        # шаблон переменных окружения
└── requirements.txt
```

## Запуск

```bash
# 1. Установите зависимости
pip install -r requirements.txt

# 2. Создайте .env из шаблона
cp .env.example .env
# Заполните SECRET_KEY, EMAIL_USER, EMAIL_PASS

# 3. Запустите
python main.py
```

## Переменные окружения

| Переменная   | Обязательна | Описание |
|---|---|---|
| `SECRET_KEY` | ✅ Да | Секретный ключ для JWT-токенов |
| `EMAIL_USER` | Нет | Gmail-адрес для отправки писем |
| `EMAIL_PASS` | Нет | Пароль приложения Gmail |
| `APP_BASE_URL` | Нет | URL сайта (для ссылок в письмах, по умолчанию localhost:8000) |
=======
# starthub33
asd
>>>>>>> 28f86386ae969ee7bb8889089b2ca47995066c1d
