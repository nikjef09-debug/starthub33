"""
Email-сервис StartHub
SMTP mail.ru, все отправки в фоне (asyncio task).
"""
import asyncio
import smtplib
import logging
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from typing import Optional

from core.config import EMAIL_USER, EMAIL_PASS, APP_BASE_URL

logger = logging.getLogger("email_service")

SMTP_HOST = "smtp.mail.ru"
SMTP_PORT = 465
SMTP_USER = EMAIL_USER
SMTP_PASS = EMAIL_PASS
FROM_NAME = "StartHub"
FROM_ADDR = SMTP_USER or "noreply@starthub33.ru"


# ── Низкоуровневая отправка ────────────────────────────────────────────────────

def _send_sync(to: str, subject: str, html_body: str, attachment_path: Optional[str] = None) -> None:
    if not SMTP_USER or not SMTP_PASS:
        logger.warning(f"Email skipped (no credentials configured): {subject} → {to}")
        return
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{FROM_NAME} <{FROM_ADDR}>"
    msg["To"]      = to
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    if attachment_path:
        p = Path(attachment_path)
        if p.exists():
            with open(p, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f'attachment; filename="{p.name}"')
            msg.attach(part)
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15) as server:
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(FROM_ADDR, [to], msg.as_string())
    logger.info(f"Email sent → {to} | {subject}")


async def _send_async(to: str, subject: str, html_body: str, attachment_path: Optional[str] = None):
    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, lambda: _send_sync(to, subject, html_body, attachment_path))
    except Exception as e:
        logger.error(f"Email ERROR → {to}: {e}")


def send_background(to: str, subject: str, html_body: str, attachment_path: Optional[str] = None):
    asyncio.create_task(_send_async(to, subject, html_body, attachment_path))


# ── Базовый HTML-шаблон письма ─────────────────────────────────────────────────

def _wrap(title: str, body_inner: str, subtitle: str = "") -> str:
    sub_html = f'<div class="header-sub">{subtitle}</div>' if subtitle else ""
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,'Segoe UI',Arial,sans-serif;background:#060e0a;color:#e2e8f0}}
.ew{{max-width:640px;margin:0 auto;padding:32px 16px}}
.ec{{background:#0c1a13;border-radius:20px;overflow:hidden;border:1px solid rgba(16,185,129,0.15)}}
.hd{{background:linear-gradient(135deg,#064e2d 0%,#0a3322 60%,#071a11 100%);padding:40px 40px 32px;position:relative;overflow:hidden}}
.hd::before{{content:'';position:absolute;top:-80px;right:-60px;width:240px;height:240px;border-radius:50%;background:rgba(16,185,129,0.1)}}
.hd::after{{content:'';position:absolute;bottom:-50px;left:-50px;width:180px;height:180px;border-radius:50%;background:rgba(5,150,105,0.07)}}
.logo{{display:flex;align-items:center;gap:12px;margin-bottom:28px;position:relative;z-index:1}}
.logo-ic{{width:42px;height:42px;background:linear-gradient(135deg,#22c55e,#15803d);border-radius:11px;display:flex;align-items:center;justify-content:center}}
.logo-tx{{font-size:22px;font-weight:800;color:#fff;letter-spacing:-0.5px}}
.logo-tx span{{color:#4ade80}}
.header-title{{font-size:30px;font-weight:800;color:#fff;letter-spacing:-0.7px;line-height:1.2;margin-bottom:8px;position:relative;z-index:1}}
.header-sub{{font-size:14px;color:rgba(255,255,255,0.55);position:relative;z-index:1;margin-top:4px}}
.bd{{padding:36px 40px}}
.greeting{{font-size:16px;color:#a7f3d0;margin-bottom:22px;font-weight:500}}
.txt{{font-size:14px;color:rgba(226,232,240,0.82);line-height:1.75;margin-bottom:18px}}
.ic{{background:rgba(16,185,129,0.07);border:1px solid rgba(16,185,129,0.15);border-radius:16px;padding:24px 28px;margin:24px 0}}
.ic-title{{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;color:#4ade80;margin-bottom:18px}}
.ir{{display:flex;justify-content:space-between;align-items:flex-start;padding:11px 0;border-bottom:1px solid rgba(255,255,255,0.05);font-size:14px}}
.ir:last-child{{border-bottom:none;padding-bottom:0}}
.il{{color:rgba(226,232,240,0.45);min-width:150px}}
.iv{{color:#e2e8f0;font-weight:600;text-align:right;max-width:300px}}
.iv.hl{{color:#4ade80;font-size:20px;font-weight:800}}
.iv.am{{color:#4ade80;font-size:32px;font-weight:800;letter-spacing:-1px}}
.ab{{text-align:center;padding:28px 24px;background:rgba(16,185,129,0.06);border-radius:14px;margin:24px 0;border:1px solid rgba(16,185,129,0.18)}}
.ab-label{{font-size:11px;color:rgba(226,232,240,0.4);text-transform:uppercase;letter-spacing:1px;margin-bottom:10px}}
.ab-value{{font-size:48px;font-weight:800;color:#4ade80;letter-spacing:-2px;line-height:1}}
.ab-sub{{font-size:13px;color:rgba(226,232,240,0.4);margin-top:8px}}
.btn{{display:inline-block;background:linear-gradient(135deg,#22c55e,#15803d);color:#fff;padding:16px 36px;border-radius:12px;text-decoration:none;font-weight:700;font-size:15px;text-align:center}}
.btn-wrap{{text-align:center;margin:32px 0}}
.div{{height:1px;background:rgba(255,255,255,0.05);margin:28px 0}}
.warn{{background:rgba(251,191,36,0.08);border:1px solid rgba(251,191,36,0.2);border-radius:12px;padding:16px 20px;margin:20px 0;font-size:13px;color:#fbbf24;line-height:1.6}}
.ok{{background:rgba(74,222,128,0.08);border:1px solid rgba(74,222,128,0.2);border-radius:12px;padding:16px 20px;margin:20px 0;font-size:14px;color:#4ade80;font-weight:600}}
.sb{{display:inline-block;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:700}}
.sb-ok{{background:rgba(74,222,128,0.15);color:#4ade80;border:1px solid rgba(74,222,128,0.3)}}
.sb-pend{{background:rgba(251,191,36,0.15);color:#fbbf24;border:1px solid rgba(251,191,36,0.3)}}
.user-card{{background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);border-radius:12px;padding:18px 22px;margin:20px 0;display:flex;align-items:center;gap:16px}}
.user-ava{{width:48px;height:48px;border-radius:50%;background:linear-gradient(135deg,#22c55e,#15803d);display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:700;color:#fff;flex-shrink:0}}
.user-name{{font-size:16px;font-weight:700;color:#e2e8f0;margin-bottom:2px}}
.user-meta{{font-size:12px;color:rgba(226,232,240,0.4)}}
.ft{{padding:22px 40px;border-top:1px solid rgba(255,255,255,0.05);display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px}}
.ft-logo{{font-size:15px;font-weight:800;color:#4ade80;letter-spacing:-0.3px}}
.ft-tx{{font-size:12px;color:rgba(226,232,240,0.25)}}
.tx-id{{font-family:monospace;font-size:12px;color:rgba(226,232,240,0.3);background:rgba(255,255,255,0.04);padding:3px 8px;border-radius:4px}}
</style>
</head>
<body>
<div class="ew">
<div class="ec">
<div class="hd">
  <div class="logo">
    <div class="logo-ic"><svg width="20" height="20" viewBox="0 0 24 24"><polygon points="12,2 2,20 22,20" fill="white"/></svg></div>
    <div class="logo-tx">Start<span>Hub</span></div>
  </div>
  <div class="header-title">{title}</div>
  {sub_html}
</div>
<div class="bd">
{body_inner}
</div>
<div class="ft">
  <div class="ft-logo">StartHub</div>
  <div class="ft-tx">© 2025 StartHub · {FROM_ADDR} · Автоматическое письмо</div>
</div>
</div>
</div>
</body>
</html>"""


def _fmt(amount) -> str:
    if amount is None:
        return "не указана"
    return f"{float(amount):,.0f} ₽".replace(",", " ")


def _now_str() -> str:
    return datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")


# ── Шаблонные письма ───────────────────────────────────────────────────────────

def send_verification_email(email: str, token: str, base_url: str = None):
    link = f"{base_url or APP_BASE_URL}/verify-email/{token}"
    html = _wrap("Подтвердите email", f"""
<p class="greeting">Добро пожаловать в StartHub!</p>
<p class="txt">Для завершения регистрации подтвердите ваш адрес электронной почты.<br>
Ссылка действительна <strong style="color:#fbbf24">24 часа</strong>.</p>
<div class="btn-wrap"><a href="{link}" class="btn">✉️ Подтвердить email</a></div>
<div class="warn">⚠️ Если вы не регистрировались на StartHub — просто проигнорируйте это письмо.</div>
""", subtitle="Подтверждение регистрации")
    send_background(email, "Подтвердите ваш email — StartHub", html)


def send_reset_email(email: str, token: str, base_url: str = None):
    link = f"{base_url or APP_BASE_URL}/reset-password/{token}"
    html = _wrap("Сброс пароля", f"""
<p class="greeting">Запрос на сброс пароля</p>
<p class="txt">Вы запросили сброс пароля для аккаунта <strong style="color:#e2e8f0">{email}</strong>.<br>
Ссылка действительна <strong style="color:#fbbf24">2 часа</strong>.</p>
<div class="btn-wrap"><a href="{link}" class="btn">🔑 Сбросить пароль</a></div>
<div class="warn">⚠️ Если вы не запрашивали сброс — просто проигнорируйте это письмо. Ваш пароль останется прежним.</div>
""", subtitle="Запрос создан " + _now_str())
    send_background(email, "Сброс пароля — StartHub", html)


def send_deal_created(to: str, deal_id: int, startup_title: str, buyer_name: str, amount=None):
    amt_str = _fmt(amount) if amount else "сумма к обсуждению"
    html = _wrap("Новая сделка", f"""
<p class="greeting">По вашему стартапу создана новая заявка на покупку</p>
<div class="ab">
  <div class="ab-label">Предложение покупателя</div>
  <div class="ab-value">{_fmt(amount) if amount else "—"}</div>
  <div class="ab-sub">Сделка #{deal_id}</div>
</div>
<div class="ic">
  <div class="ic-title">Детали сделки</div>
  <div class="ir"><span class="il">Стартап</span><span class="iv">{startup_title}</span></div>
  <div class="ir"><span class="il">Покупатель</span><span class="iv">{buyer_name}</span></div>
  <div class="ir"><span class="il">Предложение</span><span class="iv" style="color:#4ade80">{amt_str}</span></div>
  <div class="ir"><span class="il">Номер сделки</span><span class="iv"><span class="tx-id">#{deal_id}</span></span></div>
  <div class="ir"><span class="il">Дата</span><span class="iv">{_now_str()}</span></div>
  <div class="ir"><span class="il">Статус</span><span class="iv"><span class="sb sb-pend">На рассмотрении</span></span></div>
</div>
<p class="txt">Войдите в личный кабинет, чтобы принять или отклонить предложение.</p>
<div class="btn-wrap"><a href="{APP_BASE_URL}/deal/{deal_id}" class="btn">📋 Открыть сделку</a></div>
""", subtitle=f"Стартап «{startup_title}»")
    send_background(to, f"Новая сделка по «{startup_title}» — StartHub", html)


def send_deal_status_changed(to: str, deal_id: int, startup_title: str, new_status: str):
    status_map = {
        "pending":     ("На рассмотрении", "sb-pend", "⏳"),
        "active":      ("Активна",          "sb-ok",   "✅"),
        "documents":   ("Загрузка документов", "sb-pend", "📄"),
        "closed_ok":   ("Успешно закрыта",  "sb-ok",   "🎉"),
        "closed_fail": ("Закрыта неудачно", "",        "❌"),
    }
    label, css, icon = status_map.get(new_status, (new_status, "", "ℹ️"))
    is_closed_ok = new_status == "closed_ok"
    html = _wrap(f"{icon} Статус сделки изменён", f"""
<p class="greeting">Статус вашей сделки обновился</p>
<div class="ic">
  <div class="ic-title">Информация о сделке</div>
  <div class="ir"><span class="il">Стартап</span><span class="iv">{startup_title}</span></div>
  <div class="ir"><span class="il">Номер сделки</span><span class="iv"><span class="tx-id">#{deal_id}</span></span></div>
  <div class="ir"><span class="il">Новый статус</span><span class="iv"><span class="sb {css}">{label}</span></span></div>
  <div class="ir"><span class="il">Обновлено</span><span class="iv">{_now_str()}</span></div>
</div>
{'<div class="ok">🎉 Поздравляем! Сделка успешно завершена. Документы и акт выполнения доступны в личном кабинете.</div>' if is_closed_ok else ''}
<div class="btn-wrap"><a href="{APP_BASE_URL}/deal/{deal_id}" class="btn">📋 Открыть сделку</a></div>
""", subtitle=f"Сделка #{deal_id} · {startup_title}")
    send_background(to, f"Статус сделки #{deal_id} изменён — StartHub", html)


def send_document_uploaded(to: str, deal_id: int, startup_title: str, filename: str, uploader: str):
    html = _wrap("📎 Загружен новый документ", f"""
<p class="greeting">В вашей сделке появился новый документ</p>
<div class="ic">
  <div class="ic-title">Детали документа</div>
  <div class="ir"><span class="il">Файл</span><span class="iv" style="color:#4ade80">📄 {filename}</span></div>
  <div class="ir"><span class="il">Загрузил</span><span class="iv">{uploader}</span></div>
  <div class="ir"><span class="il">Стартап</span><span class="iv">{startup_title}</span></div>
  <div class="ir"><span class="il">Сделка</span><span class="iv"><span class="tx-id">#{deal_id}</span></span></div>
  <div class="ir"><span class="il">Дата</span><span class="iv">{_now_str()}</span></div>
</div>
<div class="btn-wrap"><a href="{APP_BASE_URL}/deal/{deal_id}" class="btn">📋 Открыть сделку</a></div>
""", subtitle=f"Сделка #{deal_id} · {startup_title}")
    send_background(to, f"Новый документ в сделке #{deal_id} — StartHub", html)


def send_deal_completed(to: str, deal_id: int, startup_title: str, final_amount=None):
    html = _wrap("🎉 Сделка успешно завершена!", f"""
<p class="greeting">Поздравляем с успешным завершением сделки!</p>
<div class="ab">
  <div class="ab-label">Итоговая сумма сделки</div>
  <div class="ab-value">{_fmt(final_amount)}</div>
  <div class="ab-sub">Сделка #{deal_id}</div>
</div>
<div class="ic">
  <div class="ic-title">Итоги сделки</div>
  <div class="ir"><span class="il">Стартап</span><span class="iv">{startup_title}</span></div>
  <div class="ir"><span class="il">Итоговая сумма</span><span class="iv" style="color:#4ade80">{_fmt(final_amount)}</span></div>
  <div class="ir"><span class="il">Номер сделки</span><span class="iv"><span class="tx-id">#{deal_id}</span></span></div>
  <div class="ir"><span class="il">Дата закрытия</span><span class="iv">{_now_str()}</span></div>
  <div class="ir"><span class="il">Статус</span><span class="iv"><span class="sb sb-ok">Закрыта успешно</span></span></div>
</div>
<div class="ok">✅ Акт выполнения работ сформирован и доступен в разделе «Документы» вашей сделки.</div>
<div class="btn-wrap"><a href="{APP_BASE_URL}/deal/{deal_id}" class="btn">📋 Открыть сделку</a></div>
""", subtitle=f"Сделка #{deal_id} · {startup_title}")
    send_background(to, f"Сделка завершена — {startup_title} — StartHub", html)


def send_ticket_reply(to: str, ticket_id: int, subject: str, reply: str):
    html = _wrap("💬 Ответ на ваш тикет", f"""
<p class="greeting">Служба поддержки ответила на ваш запрос</p>
<div class="ic">
  <div class="ic-title">Ваш запрос</div>
  <div class="ir"><span class="il">Тема</span><span class="iv">{subject}</span></div>
  <div class="ir"><span class="il">Тикет</span><span class="iv"><span class="tx-id">#{ticket_id}</span></span></div>
  <div class="ir"><span class="il">Дата ответа</span><span class="iv">{_now_str()}</span></div>
</div>
<div style="background:rgba(255,255,255,0.03);border-left:3px solid #22c55e;border-radius:0 10px 10px 0;padding:18px 22px;margin:20px 0">
  <div style="font-size:11px;color:#4ade80;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-bottom:10px">Ответ менеджера</div>
  <div style="font-size:14px;color:rgba(226,232,240,0.85);line-height:1.7">{reply}</div>
</div>
<div class="btn-wrap"><a href="{APP_BASE_URL}/support" class="btn">💬 Перейти в поддержку</a></div>
""", subtitle=f"Тикет #{ticket_id}")
    send_background(to, f"Ответ на тикет: {subject} — StartHub", html)


def send_contact_form(to: str, name: str, email: str, message: str):
    html = _wrap("📬 Новая заявка с сайта", f"""
<p class="greeting">Получена новая заявка через форму обратной связи</p>
<div class="ic">
  <div class="ic-title">Данные отправителя</div>
  <div class="ir"><span class="il">Имя</span><span class="iv">{name}</span></div>
  <div class="ir"><span class="il">Email</span><span class="iv">{email}</span></div>
  <div class="ir"><span class="il">Дата</span><span class="iv">{_now_str()}</span></div>
</div>
<div style="background:rgba(255,255,255,0.03);border-left:3px solid #6366f1;border-radius:0 10px 10px 0;padding:18px 22px;margin:20px 0">
  <div style="font-size:11px;color:#818cf8;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-bottom:10px">Сообщение</div>
  <div style="font-size:14px;color:rgba(226,232,240,0.85);line-height:1.7">{message}</div>
</div>
""", subtitle=f"От: {name} &lt;{email}&gt;")
    send_background(to, f"Заявка от {name} — StartHub", html)


def send_payment_receipt(to: str, deal_id: int, startup_title: str, amount: float,
                          method_label: str, receipt_path: Optional[str] = None):
    html = _wrap("🧾 Квитанция об оплате", f"""
<p class="greeting">Ваш платёж зарегистрирован</p>
<div class="ab">
  <div class="ab-label">Сумма платежа</div>
  <div class="ab-value">{_fmt(amount)}</div>
  <div class="ab-sub">{method_label} · Сделка #{deal_id}</div>
</div>
<div class="ic">
  <div class="ic-title">Детали платежа</div>
  <div class="ir"><span class="il">Стартап</span><span class="iv">{startup_title}</span></div>
  <div class="ir"><span class="il">Номер сделки</span><span class="iv"><span class="tx-id">#{deal_id}</span></span></div>
  <div class="ir"><span class="il">Сумма</span><span class="iv hl">{_fmt(amount)}</span></div>
  <div class="ir"><span class="il">Способ оплаты</span><span class="iv">{method_label}</span></div>
  <div class="ir"><span class="il">Дата и время</span><span class="iv">{_now_str()}</span></div>
  <div class="ir"><span class="il">Статус</span><span class="iv"><span class="sb sb-pend">Ожидает подтверждения</span></span></div>
</div>
{'<div class="ok">📎 Чек прикреплён к этому письму.</div>' if receipt_path else ''}
<div class="warn">⚠️ Платёж будет подтверждён менеджером. Вы получите уведомление об изменении статуса.</div>
<div class="btn-wrap"><a href="{APP_BASE_URL}/deal/{deal_id}" class="btn">📋 Открыть сделку</a></div>
""", subtitle=f"Сделка #{deal_id} · {startup_title}")
    send_background(to, f"Квитанция об оплате — Сделка #{deal_id} — StartHub", html, receipt_path)


def send_deposit_receipt(to: str, username: str, user_id: int, tx_id: int,
                          amount: float, method: str, balance_after: float):
    method_labels = {"online": "Банковская карта", "qr": "QR / СБП", "bank": "Банковский перевод"}
    method_label = method_labels.get(method, method)
    initial = (username[0].upper() if username else "U")
    html = _wrap("💳 Кошелёк пополнен", f"""
<p class="greeting">Ваш баланс успешно пополнен!</p>
<div class="ab">
  <div class="ab-label">Сумма пополнения</div>
  <div class="ab-value">+{_fmt(amount)}</div>
  <div class="ab-sub">Транзакция #{tx_id}</div>
</div>
<div class="user-card">
  <div class="user-ava">{initial}</div>
  <div>
    <div class="user-name">@{username}</div>
    <div class="user-meta">ID пользователя: #{user_id} · {to}</div>
  </div>
</div>
<div class="ic">
  <div class="ic-title">Детали операции</div>
  <div class="ir"><span class="il">Номер транзакции</span><span class="iv"><span class="tx-id">#{tx_id}</span></span></div>
  <div class="ir"><span class="il">Сумма</span><span class="iv hl">+{_fmt(amount)}</span></div>
  <div class="ir"><span class="il">Способ пополнения</span><span class="iv">{method_label}</span></div>
  <div class="ir"><span class="il">Дата и время</span><span class="iv">{_now_str()}</span></div>
  <div class="ir"><span class="il">Новый баланс</span><span class="iv" style="color:#fbbf24;font-weight:700">{_fmt(balance_after)}</span></div>
  <div class="ir"><span class="il">Статус</span><span class="iv"><span class="sb sb-ok">Зачислено</span></span></div>
</div>
<div class="btn-wrap"><a href="{APP_BASE_URL}/wallet" class="btn">💼 Перейти в кошелёк</a></div>
""", subtitle=f"Транзакция #{tx_id} · {_now_str()}")
    send_background(to, f"Кошелёк пополнен на {_fmt(amount)} — StartHub", html)


def send_bulk_email(to: str, subject: str, body_html: str):
    html = _wrap(subject, f'<p class="txt">{body_html}</p>', subtitle="Сообщение от платформы StartHub")
    send_background(to, subject, html)
