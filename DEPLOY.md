# Деплой StartHub на VPS (Ubuntu 22.04)

## 1. Установка зависимостей на сервере

```bash
sudo apt update && sudo apt install -y python3.12 python3.12-venv python3-pip nginx certbot python3-certbot-nginx
```

## 2. Загрузка проекта

```bash
# Скопировать файлы на сервер (из Windows):
scp -r . root@ВАШ_IP:/opt/starthub

# На сервере:
cd /opt/starthub
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 3. Настройка .env

```bash
cp .env.example .env
nano .env
```

Заполните `.env`:
```
SECRET_KEY=<сгенерируйте: python3 -c "import secrets; print(secrets.token_hex(32))">
EMAIL_USER=starthub33@internet.ru
EMAIL_PASS=<пароль из настроек почты mail.ru>
APP_BASE_URL=https://starthub33.ru
CONTACT_EMAIL=info@starthub33.ru
```

## 4. Миграция базы данных

```bash
source venv/bin/activate
python migrate.py
```

## 5. Systemd сервис

```bash
nano /etc/systemd/system/starthub.service
```

```ini
[Unit]
Description=StartHub FastAPI App
After=network.target

[Service]
User=www-data
WorkingDirectory=/opt/starthub
ExecStart=/opt/starthub/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2
Restart=always
RestartSec=3
Environment="PATH=/opt/starthub/venv/bin"

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable starthub
systemctl start starthub
systemctl status starthub
```

## 6. Nginx как reverse proxy

```bash
nano /etc/nginx/sites-available/starthub33.ru
```

```nginx
server {
    listen 80;
    server_name starthub33.ru;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name starthub33.ru;

    ssl_certificate     /etc/letsencrypt/live/starthub33.ru/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/starthub33.ru/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;

    # Статика через nginx (быстрее, чем через Python)
    location /static/ {
        alias /opt/starthub/static/;
        expires 7d;
        add_header Cache-Control "public";
    }

    # WebSocket для чата
    location /ws/ {
        proxy_pass         http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_set_header   Host $host;
    }

    # Приложение
    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
        client_max_body_size 20M;
    }
}
```

```bash
ln -s /etc/nginx/sites-available/starthub33.ru /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx
```

## 7. SSL сертификат (Let's Encrypt)

```bash
certbot --nginx -d starthub33.ru
```

## 8. Шрифты для PDF (если нужны)

```bash
apt install -y fonts-liberation fonts-dejavu
```

## Полезные команды

```bash
systemctl restart starthub     # перезапустить
journalctl -u starthub -f      # смотреть логи в реальном времени
systemctl status starthub      # статус сервиса
```
