import asyncio
import smtplib
from concurrent.futures import ThreadPoolExecutor
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

import structlog

from app.core.config import settings

log = structlog.get_logger()

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="smtp")


def _send_sync(to: str, subject: str, html_body: str, text_body: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr((settings.smtp_from_name, settings.smtp_from_email))
    msg["To"] = to
    if settings.smtp_reply_to:
        msg["Reply-To"] = settings.smtp_reply_to

    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    if settings.smtp_security == "ssl":
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port) as smtp:
            smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.sendmail(settings.smtp_from_email, to, msg.as_string())
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
            if settings.smtp_security == "starttls":
                smtp.starttls()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.sendmail(settings.smtp_from_email, to, msg.as_string())


async def send_email(to: str, subject: str, html_body: str, text_body: str) -> None:
    if not settings.smtp_enabled:
        log.info("smtp_disabled_skipping_email", to=to, subject=subject)
        return

    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(_executor, _send_sync, to, subject, html_body, text_body)
    except Exception as exc:
        # Log and swallow – email failure must not break the calling flow
        log.error("smtp_send_failed", to=to, subject=subject, error=str(exc))


async def send_password_reset_email(to: str, reset_url: str) -> None:
    subject = "Passwort zurücksetzen – CashFlow"
    text_body = (
        f"Klicke auf folgenden Link, um dein Passwort zurückzusetzen:\n\n"
        f"{reset_url}\n\n"
        f"Der Link ist 1 Stunde gültig. Falls du keine Zurücksetzung angefordert "
        f"hast, kannst du diese E-Mail ignorieren."
    )
    html_body = f"""<!DOCTYPE html>
<html>
<body style="font-family: Inter, sans-serif; color: #1e293b; max-width: 600px; margin: 0 auto; padding: 24px;">
  <h2 style="color: #4f46e5;">Passwort zurücksetzen</h2>
  <p>Klicke auf folgenden Button, um dein Passwort zurückzusetzen:</p>
  <p>
    <a href="{reset_url}"
       style="display:inline-block;background:#4f46e5;color:#fff;padding:12px 24px;border-radius:6px;text-decoration:none;font-weight:600;">
      Passwort zurücksetzen
    </a>
  </p>
  <p style="color:#64748b;font-size:14px;">
    Der Link ist 1 Stunde gültig.<br>
    Falls du keine Zurücksetzung angefordert hast, kannst du diese E-Mail ignorieren.
  </p>
</body>
</html>"""
    await send_email(to, subject, html_body, text_body)


async def send_invitation_email(to: str, invite_url: str, expires_days: int) -> None:
    subject = "Du wurdest eingeladen – CashFlow"
    text_body = (
        f"Du wurdest eingeladen, CashFlow zu nutzen.\n\n"
        f"Klicke auf folgenden Link, um dein Passwort zu setzen und dich anzumelden:\n\n"
        f"{invite_url}\n\n"
        f"Der Link ist {expires_days} Tage gültig.\n"
        f"Falls du diese Einladung nicht erwartet hast, kannst du diese E-Mail ignorieren."
    )
    html_body = f"""<!DOCTYPE html>
<html>
<body style="font-family: Inter, sans-serif; color: #1e293b; max-width: 600px; margin: 0 auto; padding: 24px;">
  <h2 style="color: #4f46e5;">Du wurdest eingeladen</h2>
  <p>Klicke auf folgenden Button, um dein Passwort zu setzen und dich anzumelden:</p>
  <p>
    <a href="{invite_url}"
       style="display:inline-block;background:#4f46e5;color:#fff;padding:12px 24px;border-radius:6px;text-decoration:none;font-weight:600;">
      Einladung annehmen
    </a>
  </p>
  <p style="color:#64748b;font-size:14px;">
    Der Link ist {expires_days} Tage gültig.<br>
    Falls du diese Einladung nicht erwartet hast, kannst du diese E-Mail ignorieren.
  </p>
</body>
</html>"""
    await send_email(to, subject, html_body, text_body)
