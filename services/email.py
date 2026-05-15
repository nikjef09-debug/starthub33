from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType as MailType

from core.config import EMAIL_USER, EMAIL_PASS, APP_BASE_URL

_mail_conf = ConnectionConfig(
    MAIL_USERNAME=EMAIL_USER or "",
    MAIL_PASSWORD=EMAIL_PASS or "",
    MAIL_FROM=EMAIL_USER or "noreply@starthub.ru",
    MAIL_FROM_NAME="StartHub",
    MAIL_PORT=587,
    MAIL_SERVER="smtp.gmail.com",
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=bool(EMAIL_USER and EMAIL_PASS),
)

fast_mail = FastMail(_mail_conf)


async def send_reset_email(email: str, token: str) -> None:
    reset_link = f"{APP_BASE_URL}/reset-password/{token}"
    message = MessageSchema(
        subject="Сброс пароля — StartHub",
        recipients=[email],
        body=f"""
        <div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;padding:32px;
                    background:#0D0C0B;color:#fff;border-radius:12px">
          <h2 style="color:#E85D26;margin-bottom:8px">StartHub</h2>
          <h3 style="margin-bottom:16px">Сброс пароля</h3>
          <p style="color:rgba(255,255,255,0.7);margin-bottom:24px">
            Вы запросили сброс пароля для аккаунта <strong>{email}</strong>.<br>
            Ссылка действительна 2 часа.
          </p>
          <a href="{reset_link}"
             style="display:inline-block;background:#E85D26;color:#fff;padding:14px 32px;
                    border-radius:8px;text-decoration:none;font-weight:600;font-size:15px">
            Сбросить пароль
          </a>
          <p style="color:rgba(255,255,255,0.4);font-size:13px;margin-top:24px">
            Если вы не запрашивали сброс — просто проигнорируйте это письмо.
          </p>
        </div>
        """,
        subtype=MailType.html,
    )
    await fast_mail.send_message(message)
