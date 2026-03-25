"""Async SMTP email service."""

import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib

from app.config import Settings

logger = logging.getLogger(__name__)


async def send_email(to: str, subject: str, html_body: str, settings: Settings | None = None) -> bool:
    """Send an HTML email via SMTP. Returns True on success."""
    if settings is None:
        settings = Settings()

    if not settings.smtp_host:
        logger.warning("SMTP not configured — skipping email to %s", to)
        return False

    msg = MIMEMultipart("alternative")
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html"))

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user or None,
            password=settings.smtp_password or None,
            use_tls=settings.smtp_use_tls,
        )
        logger.info("Email sent to %s: %s", to, subject)
        return True
    except Exception:
        logger.exception("Failed to send email to %s", to)
        return False


# ---------------------------------------------------------------------------
# Email templates
# ---------------------------------------------------------------------------

_BASE_STYLE = """
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0a0a0a; color: #e5e7eb; margin: 0; padding: 0; }
  .container { max-width: 600px; margin: 0 auto; padding: 40px 24px; }
  .card { background: #171717; border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 32px; }
  .logo { font-size: 24px; font-weight: 700; color: #f1b300; margin-bottom: 24px; }
  h1 { font-size: 20px; color: #fff; margin: 0 0 16px 0; }
  p { font-size: 15px; line-height: 1.6; color: #9ca3af; margin: 0 0 16px 0; }
  .btn { display: inline-block; background: #f1b300; color: #000; font-weight: 700; padding: 12px 28px; border-radius: 8px; text-decoration: none; font-size: 15px; }
  .footer { margin-top: 32px; font-size: 13px; color: #6b7280; text-align: center; }
  .highlight { color: #f1b300; font-weight: 600; }
</style>
"""


def waitlist_confirmation_email(name: str, position: int, frontend_url: str, status_uuid: str) -> tuple[str, str]:
    """Returns (subject, html_body) for waitlist confirmation."""
    subject = "You're on the Vandalizer Demo Waitlist!"
    html = f"""<!DOCTYPE html><html><head>{_BASE_STYLE}</head><body>
    <div class="container"><div class="card">
      <div class="logo">Vandalizer</div>
      <h1>Welcome to the waitlist, {name}!</h1>
      <p>Your demo application has been received. You are currently at position <span class="highlight">#{position}</span> on the waitlist.</p>
      <p>Your application ID is: <span class="highlight">{status_uuid}</span></p>
      <p>We activate new accounts regularly. When a spot opens up, you'll receive an email with your login credentials and full access to the platform for 2 weeks.</p>
      <p style="margin-top:24px"><a class="btn" href="{frontend_url}/demo/status/{status_uuid}">Check Your Status</a></p>
      <div class="footer">Vandalizer</div>
    </div></div></body></html>"""
    return subject, html


def activation_email(name: str, user_id: str, password: str, expires_at: str, frontend_url: str) -> tuple[str, str]:
    """Returns (subject, html_body) for demo account activation."""
    subject = "Your Vandalizer Demo Account is Ready!"
    html = f"""<!DOCTYPE html><html><head>{_BASE_STYLE}</head><body>
    <div class="container"><div class="card">
      <div class="logo">Vandalizer</div>
      <h1>Your demo account is active!</h1>
      <p>Hi {name}, great news &mdash; your Vandalizer demo account is ready to go. You have <span class="highlight">2 weeks</span> of full platform access.</p>
      <p><strong style="color:#fff">Username:</strong> {user_id}<br/>
         <strong style="color:#fff">Password:</strong> {password}</p>
      <p>Your trial expires on <span class="highlight">{expires_at}</span>.</p>
      <p style="margin-top:24px"><a class="btn" href="{frontend_url}/landing">Sign In Now</a></p>
      <div class="footer">Vandalizer</div>
    </div></div></body></html>"""
    return subject, html


def expiry_warning_email(name: str, days_left: int, expires_at: str, frontend_url: str) -> tuple[str, str]:
    """Returns (subject, html_body) for trial expiry warning."""
    subject = f"Your Vandalizer demo expires in {days_left} day{'s' if days_left != 1 else ''}"
    html = f"""<!DOCTYPE html><html><head>{_BASE_STYLE}</head><body>
    <div class="container"><div class="card">
      <div class="logo">Vandalizer</div>
      <h1>Your demo is expiring soon</h1>
      <p>Hi {name}, your Vandalizer demo trial expires on <span class="highlight">{expires_at}</span> ({days_left} day{'s' if days_left != 1 else ''} remaining).</p>
      <p>Make sure to explore any features you haven't tried yet! After expiry, your account will be locked and you'll be asked to complete a short feedback questionnaire.</p>
      <p style="margin-top:24px"><a class="btn" href="{frontend_url}/landing">Go to Vandalizer</a></p>
      <div class="footer">Vandalizer</div>
    </div></div></body></html>"""
    return subject, html


def trial_expired_email(name: str, feedback_url: str) -> tuple[str, str]:
    """Returns (subject, html_body) for trial expired notification."""
    subject = "Your Vandalizer Demo Has Ended"
    html = f"""<!DOCTYPE html><html><head>{_BASE_STYLE}</head><body>
    <div class="container"><div class="card">
      <div class="logo">Vandalizer</div>
      <h1>Thank you for trying Vandalizer!</h1>
      <p>Hi {name}, your 2-week demo trial has ended. We hope you found the platform valuable.</p>
      <p>We'd love to hear about your experience. Please take a few minutes to fill out our feedback questionnaire:</p>
      <p style="margin-top:24px"><a class="btn" href="{feedback_url}">Share Your Feedback</a></p>
      <p>Your feedback helps us improve Vandalizer for future users and researchers.</p>
      <div class="footer">Vandalizer</div>
    </div></div></body></html>"""
    return subject, html
