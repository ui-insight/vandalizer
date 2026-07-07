"""Async email service — supports SMTP and Resend providers."""

import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib
import httpx

from app.config import Settings
from app.models.email_log import EmailLog

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"

_ERROR_MAX_LEN = 500


async def _send_via_smtp(to: str, subject: str, html_body: str, settings: Settings) -> tuple[bool, str | None]:
    """Send an HTML email via SMTP. Returns (success, error_message)."""
    if not settings.smtp_host:
        logger.warning("SMTP not configured — skipping email to %s", to)
        return False, "SMTP not configured"

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
            start_tls=settings.smtp_start_tls,
        )
        logger.info("Email sent via SMTP to %s: %s", to, subject)
        return True, None
    except Exception as exc:
        logger.exception("Failed to send email via SMTP to %s", to)
        return False, f"{type(exc).__name__}: {exc}"[:_ERROR_MAX_LEN]


async def _send_via_resend(to: str, subject: str, html_body: str, settings: Settings) -> tuple[bool, str | None]:
    """Send an HTML email via the Resend API (httpx). Returns (success, error_message)."""
    if not settings.resend_api_key:
        logger.warning("Resend API key not configured — skipping email to %s", to)
        return False, "Resend API key not configured"

    from_addr = f"{settings.resend_from_name} <{settings.resend_from_email}>"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                RESEND_API_URL,
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                json={
                    "from": from_addr,
                    "to": [to],
                    "subject": subject,
                    "html": html_body,
                },
                timeout=30,
            )
            resp.raise_for_status()
        logger.info("Email sent via Resend to %s: %s", to, subject)
        return True, None
    except httpx.HTTPStatusError as exc:
        logger.exception("Failed to send email via Resend to %s", to)
        body = exc.response.text if exc.response is not None else ""
        return False, f"HTTP {exc.response.status_code}: {body}"[:_ERROR_MAX_LEN]
    except Exception as exc:
        logger.exception("Failed to send email via Resend to %s", to)
        return False, f"{type(exc).__name__}: {exc}"[:_ERROR_MAX_LEN]


async def _log_send(
    recipient: str, subject: str, email_type: str, provider: str,
    success: bool, error: str | None,
) -> None:
    """Persist an EmailLog row. Never raises."""
    try:
        await EmailLog(
            recipient=recipient,
            subject=subject,
            email_type=email_type,
            provider=provider,
            status="sent" if success else "failed",
            error=error,
        ).insert()
    except Exception:
        logger.exception("Failed to persist EmailLog for %s", recipient)


#: Brand defaults baked into the email templates below. When an admin customizes
#: branding in System Config, these are swapped out at send time (see
#: _apply_branding) so every template — current and future — is white-labeled
#: without threading branding through 20+ template signatures.
_EMAIL_DEFAULT_NAME = "Vandalizer"
_EMAIL_DEFAULT_COLOR = "#f1b300"
#: The theme's own default highlight; if highlight_color still equals this, the
#: admin hasn't picked a brand color, so leave the email gold (#f1b300) alone.
_THEME_DEFAULT_COLOR = "#eab308"


async def _apply_branding(subject: str, html_body: str) -> tuple[str, str]:
    """Swap the baked-in Vandalizer name/color for the deployment's branding.

    Best-effort: any failure (DB unavailable in a worker, etc.) falls back to the
    default Vandalizer branding rather than blocking the email. The name swap is
    case-sensitive on the capitalized product name, so lowercase URLs/domains
    (e.g. https://vandalizer.example.edu) are never rewritten.
    """
    try:
        from app.models.system_config import SystemConfig

        config = await SystemConfig.get_config()
        org = (config.org_name or "").strip()
        if org and org != _EMAIL_DEFAULT_NAME:
            subject = subject.replace(_EMAIL_DEFAULT_NAME, org)
            html_body = html_body.replace(_EMAIL_DEFAULT_NAME, org)
        color = (config.highlight_color or "").strip()
        if color and color.lower() != _THEME_DEFAULT_COLOR:
            html_body = html_body.replace(_EMAIL_DEFAULT_COLOR, color)
    except Exception:
        logger.exception("Failed to apply email branding; sending with defaults")
    return subject, html_body


async def send_email(
    to: str,
    subject: str,
    html_body: str,
    settings: Settings | None = None,
    email_type: str = "other",
) -> bool:
    """Send an HTML email using the configured provider. Returns True on success.

    Every attempt is persisted to the email_log collection for admin analytics.
    """
    if settings is None:
        settings = Settings()

    subject, html_body = await _apply_branding(subject, html_body)

    provider = settings.email_provider if settings.email_provider == "resend" else "smtp"
    if provider == "resend":
        success, error = await _send_via_resend(to, subject, html_body, settings)
    else:
        success, error = await _send_via_smtp(to, subject, html_body, settings)

    await _log_send(to, subject, email_type, provider, success, error)
    return success


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


def test_email(to: str) -> tuple[str, str]:
    """Returns (subject, html_body) for a deliverability test email."""
    subject = "Vandalizer Email Deliverability Test"
    html = f"""<!DOCTYPE html><html><head>{_BASE_STYLE}</head><body>
    <div class="container"><div class="card">
      <div class="logo">Vandalizer</div>
      <h1>Email Test</h1>
      <p>This is a test email sent to <span class="highlight">{to}</span>.</p>
      <p>If you're reading this in your <strong style="color:#fff">inbox</strong> (not spam), deliverability is working correctly.</p>
      <div class="footer">Vandalizer Email Deliverability Test</div>
    </div></div></body></html>"""
    return subject, html


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


_CODE_STYLE = (
    "font-family:'SF Mono',Monaco,Consolas,'Courier New',monospace;"
    "background:#0a0a0a;color:#fff;padding:3px 8px;border-radius:4px;"
    "border:1px solid rgba(255,255,255,0.15);font-size:14px;"
    "white-space:nowrap;user-select:all;-webkit-user-select:all;letter-spacing:0.5px;"
)


def activation_email(
    name: str,
    user_id: str,
    expires_at: str,
    frontend_url: str,
    magic_link: str | None = None,
) -> tuple[str, str]:
    """Returns (subject, html_body) for demo account activation.

    Passwordless by design: the email leads with a one-click sign-in link rather
    than an emailed password, so there's no credential to mistype, rotate, or
    leak. Users who prefer a password can set one anytime via "Forgot password".
    """
    subject = "Your Vandalizer Demo Account is Ready!"
    # Primary CTA: the one-click link. Fall back to /login only if (unexpectedly)
    # no link was minted.
    if magic_link:
        sign_in_section = f"""
      <p style="margin-top:24px"><a class="btn" href="{magic_link}">Click here to sign in</a></p>
      <p style="font-size:13px;color:#6b7280">One click — no password needed. This sign-in link works for the next 14 days. Need a fresh one later? Just request another from the trial email.</p>"""
    else:
        sign_in_section = f"""
      <p style="margin-top:24px"><a class="btn" href="{frontend_url}/login">Sign in</a></p>"""
    html = f"""<!DOCTYPE html><html><head>{_BASE_STYLE}</head><body>
    <div class="container"><div class="card">
      <div class="logo">Vandalizer</div>
      <h1>Your demo account is active!</h1>
      <p>Hi {name}, great news: your Vandalizer demo account is ready to go. You have <span class="highlight">2 weeks</span> of full platform access.</p>{sign_in_section}
      <p style="font-size:13px;color:#6b7280;margin-top:16px">Your account email is <code style="{_CODE_STYLE}">{user_id}</code>. Prefer to log in with a password? Set one anytime via <a href="{frontend_url}/login" style="color:#f1b300">Forgot password</a>.</p>
      <p>Your trial expires on <span class="highlight">{expires_at}</span>.</p>
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


def trial_expired_email(name: str, trial_end_url: str) -> tuple[str, str]:
    """Returns (subject, html_body) for the friendly end-of-trial notification.

    Links to the end-of-trial screen, where the user can pick up where they left
    off (self-serve renewal) or tell us what to build next.
    """
    subject = "Your Vandalizer trial — pick up where you left off"
    html = f"""<!DOCTYPE html><html><head>{_BASE_STYLE}</head><body>
    <div class="container"><div class="card">
      <div class="logo">Vandalizer</div>
      <h1>Your trial wrapped up — but you don't have to stop here</h1>
      <p>Hi {name}, your two weeks with Vandalizer are up. Vandalizer is an
         evolving beta built for research offices, and the feedback from trial
         users like you is actively shaping where it goes next.</p>
      <p>Want more time? You can pick up right where you left off, or tell us
         what would make Vandalizer more useful for your office — either way,
         we'll keep your access going.</p>
      <p style="margin-top:24px"><a class="btn" href="{trial_end_url}">Keep going &amp; share your thoughts</a></p>
      <p>Trial access continues as new releases come out. Thanks for helping
         build it.</p>
      <div class="footer">Vandalizer</div>
    </div></div></body></html>"""
    return subject, html


def trial_extended_email(name: str, expires_at: str, frontend_url: str) -> tuple[str, str]:
    """Returns (subject, html_body) confirming a self-serve trial renewal."""
    subject = "Your Vandalizer trial is extended"
    html = f"""<!DOCTYPE html><html><head>{_BASE_STYLE}</head><body>
    <div class="container"><div class="card">
      <div class="logo">Vandalizer</div>
      <h1>You're back in — welcome!</h1>
      <p>Hi {name}, your Vandalizer trial has been extended. You now have access
         through <span class="highlight">{expires_at}</span>.</p>
      <p>Thanks for helping shape the product. As new releases land, you'll see
         them here first.</p>
      <p style="margin-top:24px"><a class="btn" href="{frontend_url}/login">Back to Vandalizer</a></p>
      <div class="footer">Vandalizer</div>
    </div></div></body></html>"""
    return subject, html


# ---------------------------------------------------------------------------
# Password reset email
# ---------------------------------------------------------------------------


def password_reset_email(
    name: str, reset_url: str,
) -> tuple[str, str]:
    """Returns (subject, html_body) for a password reset request."""
    subject = "Reset your Vandalizer password"
    html = f"""<!DOCTYPE html><html><head>{_BASE_STYLE}</head><body>
    <div class="container"><div class="card">
      <div class="logo">Vandalizer</div>
      <h1>Password Reset</h1>
      <p>Hi {name}, we received a request to reset your password. Click the button below to choose a new one.</p>
      <p style="margin-top:24px"><a class="btn" href="{reset_url}">Reset Password</a></p>
      <p style="font-size:13px;color:#6b7280;margin-top:16px">This link expires in 1 hour. If you didn't request this, you can safely ignore this email.</p>
      <div class="footer">Vandalizer</div>
    </div></div></body></html>"""
    return subject, html


def password_set_email(
    name: str, reset_url: str,
) -> tuple[str, str]:
    """Returns (subject, html_body) for SSO-only users who don't yet have a password.

    Same token flow as a reset, but the copy reflects that they're setting a
    password for the first time and can keep using SSO afterward.
    """
    subject = "Set a password for your Vandalizer account"
    html = f"""<!DOCTYPE html><html><head>{_BASE_STYLE}</head><body>
    <div class="container"><div class="card">
      <div class="logo">Vandalizer</div>
      <h1>Set Your Password</h1>
      <p>Hi {name}, you've been signing in with single sign-on (SSO), so your account doesn't have a password yet. Click the button below to set one.</p>
      <p style="margin-top:24px"><a class="btn" href="{reset_url}">Set Password</a></p>
      <p style="font-size:13px;color:#6b7280;margin-top:16px">After setting a password you can sign in either way &mdash; SSO will keep working. This link expires in 1 hour. If you didn't request this, you can safely ignore this email.</p>
      <div class="footer">Vandalizer</div>
    </div></div></body></html>"""
    return subject, html


# ---------------------------------------------------------------------------
# Team invitation emails
# ---------------------------------------------------------------------------


def team_invite_email(
    inviter_name: str, team_name: str, role: str, accept_url: str,
) -> tuple[str, str]:
    """Returns (subject, html_body) for a team invitation."""
    subject = f"You've been invited to join {team_name} on Vandalizer"
    html = f"""<!DOCTYPE html><html><head>{_BASE_STYLE}</head><body>
    <div class="container"><div class="card">
      <div class="logo">Vandalizer</div>
      <h1>You're invited!</h1>
      <p><span class="highlight">{inviter_name}</span> has invited you to join
         <span class="highlight">{team_name}</span> as a <strong style="color:#fff">{role}</strong>.</p>
      <p>Click the button below to accept and start collaborating.</p>
      <p style="margin-top:24px"><a class="btn" href="{accept_url}">Accept Invitation</a></p>
      <p style="font-size:13px;color:#6b7280">This invitation expires in 30 days.</p>
      <div class="footer">Vandalizer</div>
    </div></div></body></html>"""
    return subject, html


# ---------------------------------------------------------------------------
# Verification status emails
# ---------------------------------------------------------------------------


def verification_status_email(
    submitter_name: str,
    item_name: str,
    new_status: str,
    reviewer_notes: str | None,
    frontend_url: str,
) -> tuple[str, str]:
    """Returns (subject, html_body) for a verification status change."""
    status_labels = {
        "approved": ("Approved", "Your submission has been verified and added to the catalog."),
        "rejected": ("Not Approved", "Your submission did not meet verification requirements."),
        "returned": ("Needs Revision", "Your submission has been returned with feedback."),
        "in_review": ("Under Review", "An examiner has started reviewing your submission."),
    }
    label, default_body = status_labels.get(new_status, (new_status.title(), ""))
    body_text = reviewer_notes or default_body
    subject = f'Verification update: "{item_name}" - {label}'

    notes_block = ""
    if reviewer_notes:
        notes_block = f"""
      <div style="margin:16px 0;padding:12px 16px;background:rgba(255,255,255,0.05);border-left:3px solid #f1b300;border-radius:4px;">
        <p style="margin:0;font-size:14px;color:#d1d5db;"><strong style="color:#fff;">Reviewer notes:</strong><br/>{reviewer_notes}</p>
      </div>"""

    html = f"""<!DOCTYPE html><html><head>{_BASE_STYLE}</head><body>
    <div class="container"><div class="card">
      <div class="logo">Vandalizer</div>
      <h1>{label}: {item_name}</h1>
      <p>Hi {submitter_name}, your verification submission for <span class="highlight">{item_name}</span> has been updated.</p>
      <p>{body_text}</p>
      {notes_block}
      <p style="margin-top:24px"><a class="btn" href="{frontend_url}/library?tab=verification">View Details</a></p>
      <div class="footer">Vandalizer</div>
    </div></div></body></html>"""
    return subject, html


# ---------------------------------------------------------------------------
# Support ticket emails
# ---------------------------------------------------------------------------


def support_reply_email(
    user_name: str, ticket_subject: str, message: str, ticket_uuid: str, frontend_url: str,
    ticket_number: int | None = None,
) -> tuple[str, str]:
    """Returns (subject, html_body) when support replies to a user's ticket."""
    num_prefix = f"[#{ticket_number}] " if ticket_number else ""
    subject = f"{num_prefix}Re: {ticket_subject}"
    label = (
        f'<span class="highlight">#{ticket_number}</span> &middot; <span class="highlight">{ticket_subject}</span>'
        if ticket_number
        else f'<span class="highlight">{ticket_subject}</span>'
    )
    html = f"""<!DOCTYPE html><html><head>{_BASE_STYLE}</head><body>
    <div class="container"><div class="card">
      <div class="logo">Vandalizer Support</div>
      <h1>New reply on your ticket</h1>
      <p>Hi {user_name}, there's a new reply on your support ticket {label}.</p>
      <div style="margin:16px 0;padding:12px 16px;background:rgba(255,255,255,0.05);border-left:3px solid #f1b300;border-radius:4px;">
        <p style="margin:0;font-size:14px;color:#d1d5db;">{message[:500]}</p>
      </div>
      <p style="margin-top:24px"><a class="btn" href="{frontend_url}/support?ticket={ticket_uuid}">View Ticket</a></p>
      <div class="footer">Vandalizer Support System</div>
    </div></div></body></html>"""
    return subject, html


def support_status_email(
    user_name: str, ticket_subject: str, new_status: str, ticket_uuid: str, frontend_url: str,
    ticket_number: int | None = None,
) -> tuple[str, str]:
    """Returns (subject, html_body) when a support ticket status changes."""
    num_prefix = f"[#{ticket_number}] " if ticket_number else ""
    subject = f"{num_prefix}Ticket {new_status}: {ticket_subject}"
    html = f"""<!DOCTYPE html><html><head>{_BASE_STYLE}</head><body>
    <div class="container"><div class="card">
      <div class="logo">Vandalizer Support</div>
      <h1>Ticket {new_status}</h1>
      <p>Hi {user_name}, your support ticket <span class="highlight">{ticket_subject}</span> has been marked as <strong style="color:#fff">{new_status}</strong>.</p>
      <p style="margin-top:24px"><a class="btn" href="{frontend_url}/support?ticket={ticket_uuid}">View Ticket</a></p>
      <div class="footer">Vandalizer Support System</div>
    </div></div></body></html>"""
    return subject, html


def support_new_message_email(
    support_name: str, ticket_subject: str, ticket_user: str, message: str,
    ticket_uuid: str, frontend_url: str,
    ticket_number: int | None = None,
) -> tuple[str, str]:
    """Returns (subject, html_body) when a user replies on a support ticket (for agents)."""
    num_prefix = f"[#{ticket_number}] " if ticket_number else ""
    subject = f"{num_prefix}New message on ticket: {ticket_subject}"
    html = f"""<!DOCTYPE html><html><head>{_BASE_STYLE}</head><body>
    <div class="container"><div class="card">
      <div class="logo">Vandalizer Support</div>
      <h1>New message on ticket</h1>
      <p>Hi {support_name}, <span class="highlight">{ticket_user}</span> replied on ticket <strong style="color:#fff">{ticket_subject}</strong>.</p>
      <div style="margin:16px 0;padding:12px 16px;background:rgba(255,255,255,0.05);border-left:3px solid #f1b300;border-radius:4px;">
        <p style="margin:0;font-size:14px;color:#d1d5db;">{message[:500]}</p>
      </div>
      <p style="margin-top:24px"><a class="btn" href="{frontend_url}/support?ticket={ticket_uuid}">View Ticket</a></p>
      <div class="footer">Vandalizer Support System</div>
    </div></div></body></html>"""
    return subject, html


def support_tag_added_email(
    support_name: str,
    ticket_subject: str,
    ticket_user: str,
    added_tags: list[str],
    actor_name: str,
    ticket_uuid: str,
    frontend_url: str,
    ticket_number: int | None = None,
) -> tuple[str, str]:
    """Returns (subject, html_body) when a support agent adds tag(s) to a ticket."""
    tag_list = ", ".join(added_tags)
    plural = "s" if len(added_tags) != 1 else ""
    num_prefix = f"[#{ticket_number}] " if ticket_number else ""
    subject = f"{num_prefix}Tag{plural} added to ticket: {ticket_subject}"
    tag_pills = "".join(
        f'<span style="display:inline-block;background:#f1b300;color:#000;'
        f'font-weight:600;font-size:13px;padding:3px 10px;border-radius:12px;'
        f'margin:0 6px 6px 0;">{t}</span>'
        for t in added_tags
    )
    html = f"""<!DOCTYPE html><html><head>{_BASE_STYLE}</head><body>
    <div class="container"><div class="card">
      <div class="logo">Vandalizer Support</div>
      <h1>Tag{plural} added to a ticket</h1>
      <p>Hi {support_name}, <span class="highlight">{actor_name}</span> added tag{plural} <strong style="color:#fff">{tag_list}</strong> to ticket <strong style="color:#fff">{ticket_subject}</strong> (from {ticket_user}).</p>
      <div style="margin:16px 0;">{tag_pills}</div>
      <p style="margin-top:24px"><a class="btn" href="{frontend_url}/support?ticket={ticket_uuid}">View Ticket</a></p>
      <div class="footer">Vandalizer Support System</div>
    </div></div></body></html>"""
    return subject, html


def support_watcher_added_email(
    watcher_name: str,
    ticket_subject: str,
    ticket_user: str,
    actor_name: str,
    first_message: str,
    ticket_uuid: str,
    frontend_url: str,
    ticket_number: int | None = None,
) -> tuple[str, str]:
    """Returns (subject, html_body) when a user is tagged as a watcher on a ticket."""
    num_prefix = f"[#{ticket_number}] " if ticket_number else ""
    subject = f"{num_prefix}You were added to a support ticket: {ticket_subject}"
    preview_block = ""
    if first_message:
        preview_block = f"""
      <div style="margin:16px 0;padding:12px 16px;background:rgba(255,255,255,0.05);border-left:3px solid #f1b300;border-radius:4px;">
        <p style="margin:0;font-size:14px;color:#d1d5db;">{first_message[:500]}</p>
      </div>"""
    html = f"""<!DOCTYPE html><html><head>{_BASE_STYLE}</head><body>
    <div class="container"><div class="card">
      <div class="logo">Vandalizer Support</div>
      <h1>You're now following a support ticket</h1>
      <p>Hi {watcher_name}, <span class="highlight">{actor_name}</span> added you to ticket <strong style="color:#fff">{ticket_subject}</strong> (opened by {ticket_user}). You'll receive updates as the ticket progresses and can reply directly.</p>
      {preview_block}
      <p style="margin-top:24px"><a class="btn" href="{frontend_url}/support?ticket={ticket_uuid}">View Ticket</a></p>
      <div class="footer">Vandalizer Support System</div>
    </div></div></body></html>"""
    return subject, html


# ---------------------------------------------------------------------------
# Approval request emails
# ---------------------------------------------------------------------------


def approval_request_email(
    reviewer_name: str, workflow_name: str, step_name: str,
    instructions: str, approval_uuid: str, frontend_url: str,
) -> tuple[str, str]:
    """Returns (subject, html_body) when a workflow needs human approval."""
    subject = f"Approval needed: {workflow_name}"
    instructions_block = ""
    if instructions:
        instructions_block = f"""
      <div style="margin:16px 0;padding:12px 16px;background:rgba(255,255,255,0.05);border-left:3px solid #f1b300;border-radius:4px;">
        <p style="margin:0;font-size:14px;color:#d1d5db;"><strong style="color:#fff;">Instructions:</strong><br/>{instructions}</p>
      </div>"""
    html = f"""<!DOCTYPE html><html><head>{_BASE_STYLE}</head><body>
    <div class="container"><div class="card">
      <div class="logo">Vandalizer</div>
      <h1>Approval Required</h1>
      <p>Hi {reviewer_name}, the workflow <span class="highlight">{workflow_name}</span> is paused at step <strong style="color:#fff">{step_name}</strong> and needs your review.</p>
      {instructions_block}
      <p style="margin-top:24px"><a class="btn" href="{frontend_url}/reviews/{approval_uuid}">Review Now</a></p>
      <div class="footer">Vandalizer</div>
    </div></div></body></html>"""
    return subject, html


def approval_resolved_email(
    owner_name: str, workflow_name: str, decision: str,
    reviewer_name: str, comments: str, frontend_url: str,
) -> tuple[str, str]:
    """Returns (subject, html_body) when an approval request is resolved."""
    subject = f"Workflow {decision}: {workflow_name}"
    comments_block = ""
    if comments:
        comments_block = f"""
      <div style="margin:16px 0;padding:12px 16px;background:rgba(255,255,255,0.05);border-left:3px solid #f1b300;border-radius:4px;">
        <p style="margin:0;font-size:14px;color:#d1d5db;"><strong style="color:#fff;">Reviewer comments:</strong><br/>{comments}</p>
      </div>"""
    html = f"""<!DOCTYPE html><html><head>{_BASE_STYLE}</head><body>
    <div class="container"><div class="card">
      <div class="logo">Vandalizer</div>
      <h1>Workflow {decision.title()}</h1>
      <p>Hi {owner_name}, your workflow <span class="highlight">{workflow_name}</span> has been <strong style="color:#fff">{decision}</strong> by {reviewer_name}.</p>
      {comments_block}
      <p style="margin-top:24px"><a class="btn" href="{frontend_url}/">View Workflow</a></p>
      <div class="footer">Vandalizer</div>
    </div></div></body></html>"""
    return subject, html


# ---------------------------------------------------------------------------
# Team member joined email
# ---------------------------------------------------------------------------


_KIND_LABELS = {
    "workflow": "workflow",
    "extraction": "extraction",
    "search_set": "search set",
    "knowledge_base": "knowledge base",
}


def team_share_email(
    sharer_name: str,
    item_kind: str,
    item_name: str,
    team_name: str,
    comment: str | None,
    view_url: str,
) -> tuple[str, str]:
    """Returns (subject, html_body) when a teammate shares an item with the team."""
    import html as html_lib

    kind_label = _KIND_LABELS.get(item_kind, item_kind.replace("_", " "))
    safe_sharer = html_lib.escape(sharer_name)
    safe_item = html_lib.escape(item_name)
    safe_team = html_lib.escape(team_name)
    safe_kind = html_lib.escape(kind_label)

    subject = f'{sharer_name} shared "{item_name}" with {team_name}'

    comment_block = ""
    if comment:
        safe_comment = html_lib.escape(comment).replace("\n", "<br/>")
        comment_block = f"""
      <div style="margin:16px 0;padding:12px 16px;background:rgba(255,255,255,0.05);border-left:3px solid #f1b300;border-radius:4px;">
        <p style="margin:0;font-size:14px;color:#d1d5db;"><strong style="color:#fff;">Note from {safe_sharer}:</strong><br/>{safe_comment}</p>
      </div>"""

    html = f"""<!DOCTYPE html><html><head>{_BASE_STYLE}</head><body>
    <div class="container"><div class="card">
      <div class="logo">Vandalizer</div>
      <h1>New {safe_kind} shared with your team</h1>
      <p><span class="highlight">{safe_sharer}</span> shared the {safe_kind}
         <span class="highlight">{safe_item}</span> with
         <strong style="color:#fff">{safe_team}</strong>.</p>
      {comment_block}
      <p style="margin-top:24px"><a class="btn" href="{view_url}">Open in Vandalizer</a></p>
      <div class="footer">Vandalizer</div>
    </div></div></body></html>"""
    return subject, html


def team_member_joined_email(
    inviter_name: str, member_name: str, team_name: str, frontend_url: str,
) -> tuple[str, str]:
    """Returns (subject, html_body) when someone accepts a team invitation."""
    subject = f"{member_name} joined {team_name}"
    html = f"""<!DOCTYPE html><html><head>{_BASE_STYLE}</head><body>
    <div class="container"><div class="card">
      <div class="logo">Vandalizer</div>
      <h1>New team member!</h1>
      <p>Hi {inviter_name}, <span class="highlight">{member_name}</span> has accepted your invitation and joined <strong style="color:#fff">{team_name}</strong>.</p>
      <p style="margin-top:24px"><a class="btn" href="{frontend_url}/teams">View Team</a></p>
      <div class="footer">Vandalizer</div>
    </div></div></body></html>"""
    return subject, html


# ---------------------------------------------------------------------------
# Quality alert email
# ---------------------------------------------------------------------------


def quality_alert_email(
    owner_name: str, item_name: str, item_kind: str, message: str, frontend_url: str,
) -> tuple[str, str]:
    """Returns (subject, html_body) when a verified item needs attention."""
    subject = f"Quality alert: {item_name}"
    html = f"""<!DOCTYPE html><html><head>{_BASE_STYLE}</head><body>
    <div class="container"><div class="card">
      <div class="logo">Vandalizer</div>
      <h1>Quality Alert</h1>
      <p>Hi {owner_name}, your verified {item_kind.replace('_', ' ')} <span class="highlight">{item_name}</span> needs attention.</p>
      <p>{message}</p>
      <p style="margin-top:24px"><a class="btn" href="{frontend_url}/library?tab=verification">View Details</a></p>
      <div class="footer">Vandalizer</div>
    </div></div></body></html>"""
    return subject, html


# ---------------------------------------------------------------------------
# Engagement emails (onboarding drip + inactivity nudge)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Recapture emails (activated demo users who haven't logged in)
# ---------------------------------------------------------------------------


_RECAPTURE_SEQUENCE = [
    {
        "subject": "Your Vandalizer demo account is waiting for you",
        "heading": "Ready when you are",
        "body": (
            "You were activated for a Vandalizer demo "
            "but we noticed you haven't logged in yet. "
            "Your credentials were included in your activation email. "
            "check your inbox (and spam folder) for an email from us."
        ),
        "cta": "Sign In Now",
    },
    {
        "subject": "Don't miss out on your Vandalizer trial",
        "heading": "Your trial clock is running",
        "body": (
            "Your 2-week Vandalizer demo is already active, but you haven't "
            "signed in yet. Every day you wait is a day less to explore the platform. "
            "If you're having trouble logging in, just reply to this email and we'll help."
        ),
        "cta": "Log In Now",
    },
    {
        "subject": "Last reminder: your Vandalizer demo expires soon",
        "heading": "Running out of time",
        "body": (
            "This is our last reminder. Your Vandalizer demo trial will expire "
            "soon and you haven't logged in yet. "
            "We'd hate for you to miss the chance to try out AI-powered document intelligence. "
            "If something went wrong with your account, reply to this email and we'll sort it out."
        ),
        "cta": "Try Vandalizer Now",
    },
]


def recapture_email(
    name: str, step: int, frontend_url: str, resend_url: str,
) -> tuple[str, str]:
    """Returns (subject, html_body) for a recapture drip email. step is 1-indexed."""
    seq = _RECAPTURE_SEQUENCE[step - 1]
    subject = seq["subject"]
    html = f"""<!DOCTYPE html><html><head>{_BASE_STYLE}</head><body>
    <div class="container"><div class="card">
      <div class="logo">Vandalizer</div>
      <h1>{seq['heading']}</h1>
      <p>Hi {name}, {seq['body']}</p>
      <p style="margin-top:24px"><a class="btn" href="{frontend_url}/login">{seq['cta']}</a></p>
      <p style="font-size:13px;color:#6b7280;margin-top:16px">Lost your credentials? <a href="{resend_url}" style="color:#f1b300">Resend them</a>.</p>
      <div class="footer">Vandalizer</div>
    </div></div></body></html>"""
    return subject, html


# ---------------------------------------------------------------------------
# Engagement emails (onboarding drip + inactivity nudge)
# ---------------------------------------------------------------------------


def onboarding_drip_email(
    name: str, step: int, module_title: str, module_description: str, frontend_url: str,
) -> tuple[str, str]:
    """Returns (subject, html_body) for an onboarding drip email."""
    subjects = {
        1: "Welcome to Vandalizer: start your certification journey",
        2: f"Ready for hands-on? {module_title} is next",
        3: f"Keep building: {module_title} awaits",
        4: "You're making great progress. Keep going!",
    }
    subject = subjects.get(step, f"Continue your certification: {module_title}")

    html = f"""<!DOCTYPE html><html><head>{_BASE_STYLE}</head><body>
    <div class="container"><div class="card">
      <div class="logo">Vandalizer</div>
      <h1>{module_title}</h1>
      <p>Hi {name}, {module_description}</p>
      <p style="margin-top:24px"><a class="btn" href="{frontend_url}/certification">Open Certification</a></p>
      <p style="font-size:13px;color:#6b7280;margin-top:16px">Complete modules to earn XP and work toward your Vandal Workflow Architect certification.</p>
      <div class="footer">Vandalizer</div>
    </div></div></body></html>"""
    return subject, html


def inactivity_nudge_email(
    name: str, days_inactive: int, new_items: list[dict], frontend_url: str,
) -> tuple[str, str]:
    """Returns (subject, html_body) for an inactivity nudge with new catalog items."""
    count = len(new_items)
    subject = f"{count} new item{'s' if count != 1 else ''} added to the catalog since your last visit"

    items_html = ""
    for item in new_items[:5]:
        kind_label = item.get("kind", "item").replace("_", " ")
        items_html += f'<li style="margin-bottom:8px"><strong style="color:#fff">{item["name"]}</strong> <span style="color:#6b7280">({kind_label})</span></li>'
    if count > 5:
        items_html += f'<li style="color:#6b7280">and {count - 5} more...</li>'

    html = f"""<!DOCTYPE html><html><head>{_BASE_STYLE}</head><body>
    <div class="container"><div class="card">
      <div class="logo">Vandalizer</div>
      <h1>New in the catalog</h1>
      <p>Hi {name}, it's been {days_inactive} days since your last visit. Here's what's new:</p>
      <ul style="padding-left:20px;margin:16px 0">{items_html}</ul>
      <p>Ask the chat to use any of these — just describe what you need.</p>
      <p style="margin-top:24px"><a class="btn" href="{frontend_url}/library?tab=catalog">Browse Catalog</a></p>
      <div class="footer">Vandalizer</div>
    </div></div></body></html>"""
    return subject, html


# ---------------------------------------------------------------------------
# Demo-request contact form (public landing-page submissions)
# ---------------------------------------------------------------------------


def demo_request_confirmation_email(name: str) -> tuple[str, str]:
    """Confirmation email sent to the requester who submitted the landing-page form."""
    subject = "Thanks for your interest in Vandalizer"
    html = f"""<!DOCTYPE html><html><head>{_BASE_STYLE}</head><body>
    <div class="container"><div class="card">
      <div class="logo">Vandalizer</div>
      <h1>We got your demo request, {name}.</h1>
      <p>Someone from the Vandalizer team will reach out within one business day to schedule a walkthrough tailored to your office's workflows.</p>
      <p>In the meantime, feel free to explore the docs or read about how we validate every chat reply with real test cases.</p>
      <div class="footer">Vandalizer &middot; AI for Research Administration &middot; University of Idaho</div>
    </div></div></body></html>"""
    return subject, html


def demo_request_admin_notification_email(
    name: str, email: str, institution: str, role: str, message: str,
) -> tuple[str, str]:
    """Admin-side notification email for a new demo-request submission."""
    subject = f"[Demo Request] {name} — {institution}"
    msg_html = (message or "<em>No message provided.</em>").replace("\n", "<br/>")
    html = f"""<!DOCTYPE html><html><head>{_BASE_STYLE}</head><body>
    <div class="container"><div class="card">
      <div class="logo">Vandalizer</div>
      <h1>New demo request</h1>
      <p><strong style="color:#fff">Name:</strong> {name}<br/>
         <strong style="color:#fff">Email:</strong> <a href="mailto:{email}" style="color:#f1b300">{email}</a><br/>
         <strong style="color:#fff">Institution:</strong> {institution}<br/>
         <strong style="color:#fff">Role:</strong> {role}</p>
      <div style="margin:16px 0;padding:12px 16px;background:rgba(255,255,255,0.05);border-left:3px solid #f1b300;border-radius:4px;">
        <p style="margin:0;font-size:14px;color:#d1d5db;"><strong style="color:#fff;">Message:</strong><br/>{msg_html}</p>
      </div>
      <div class="footer">Submitted via vandalizer.ai landing page</div>
    </div></div></body></html>"""
    return subject, html


# ---------------------------------------------------------------------------
# v5.0 launch announcement (sent once to existing users)
# ---------------------------------------------------------------------------


def v5_launch_announcement_email(name: str, frontend_url: str) -> tuple[str, str]:
    """Subject + HTML for the one-time v5.0 agentic-chat announcement."""
    subject = "Vandalizer 5.0 is here — chat with your documents, validated by default"
    html = f"""<!DOCTYPE html><html><head>{_BASE_STYLE}</head><body>
    <div class="container"><div class="card">
      <div class="logo">Vandalizer 5.0</div>
      <h1>Hi {name} — you now have a fully agentic Vandalizer.</h1>
      <p>We just shipped the biggest change to Vandalizer since it launched. The chat now <strong style="color:#fff">drives the whole platform</strong>:</p>
      <ul style="padding-left:20px;margin:16px 0;color:#d1d5db">
        <li style="margin-bottom:8px">Search documents and knowledge bases in natural language</li>
        <li style="margin-bottom:8px">Run validated extractions — with quality scores shown inline</li>
        <li style="margin-bottom:8px">Dispatch workflows and watch each step execute live</li>
        <li style="margin-bottom:8px">Build new knowledge bases and test cases from the conversation</li>
      </ul>
      <p>Every tool result shows its sources and its accuracy. That's the part generic AI chat can't give you.</p>
      <p style="margin-top:24px"><a class="btn" href="{frontend_url}/">Try the new chat</a></p>
      <p style="font-size:13px;color:#6b7280;margin-top:16px">Want a tour? Open the Certification panel — Module 1 walks through the agentic chat in about 10 minutes.</p>
      <div class="footer">Vandalizer 5.0 &middot; Fully Agentic</div>
    </div></div></body></html>"""
    return subject, html


# ---------------------------------------------------------------------------
# Agentic chat tutorial drip (5-step sequence for new users)
# ---------------------------------------------------------------------------

_AGENTIC_DRIP_STEPS = [
    {
        "subject": "Step 1 of 5: Ask Vandalizer what's in your documents",
        "heading": "Start a conversation, not a menu hunt",
        "body": (
            "Open the chat and say: <em>\"What documents do I have about NIH proposals?\"</em> "
            "The agent searches across your workspace and lists matches — with folder context "
            "and page counts. No clicking through file trees."
        ),
        "cta": "Try a search prompt",
    },
    {
        "subject": "Step 2 of 5: Get answers from your knowledge bases, with sources",
        "heading": "Grounded answers, citations you can click",
        "body": (
            "Every KB reply shows the exact passages it used. Click any snippet to jump to the "
            "source document at the cited line. No hallucinated answers hiding in long paragraphs."
        ),
        "cta": "Query a knowledge base",
    },
    {
        "subject": "Step 3 of 5: Run an extraction and see the quality score",
        "heading": "Not just an answer — a trustworthy answer",
        "body": (
            "When the agent runs an extraction, it shows accuracy, consistency, and the number "
            "of test cases behind the result. Tiers are color-coded so you can tell at a glance "
            "whether a result is ready to act on."
        ),
        "cta": "Run your first extraction",
    },
    {
        "subject": "Step 4 of 5: Dispatch a workflow by describing what you need",
        "heading": "Your verified workflows, one sentence away",
        "body": (
            "Say <em>\"Run the NIH compliance check on this proposal\"</em> and the agent picks "
            "the right workflow, runs it, and streams each step. Approval gates still pause "
            "for a human when needed."
        ),
        "cta": "Try a workflow prompt",
    },
    {
        "subject": "Step 5 of 5: Make the system smarter by verifying results",
        "heading": "Build your test-case library in one click",
        "body": (
            "When an extraction looks right, ask the agent to turn it into a test case. The "
            "guided verification modal lets you confirm or correct each field. Over time, this "
            "is what powers the quality scores your team can trust."
        ),
        "cta": "Open guided verification",
    },
]


# Role-specific overrides for drip step copy. Each entry swaps the example
# prompt / scenario so the drip speaks to the recipient's day-to-day work.
_ROLE_OVERRIDES: dict[str, dict[int, dict[str, str]]] = {
    "pi": {
        0: {
            "body": (
                "Open the chat and say: <em>\"What documents do I have related to my current R01?\"</em> "
                "The agent pulls the proposal, progress reports, and any budget docs it can find — "
                "no file-tree archaeology."
            ),
        },
        3: {
            "body": (
                "Say <em>\"Extract the aims and budget from my R01 resubmission and check it against "
                "my last progress report\"</em> — the agent runs the right workflow and pauses at the "
                "approval gate if your team requires one."
            ),
        },
    },
    "compliance": {
        2: {
            "body": (
                "When the agent runs a compliance-check extraction, it shows accuracy, consistency, and "
                "the number of ground-truth test cases behind the template. For audit documentation, "
                "every score ties back to a persisted ValidationRun you can point to."
            ),
        },
    },
    "sponsored_programs": {
        0: {
            "body": (
                "Open the chat and say: <em>\"What proposals does OSP have due this month?\"</em> "
                "The agent searches by deadline metadata across your office's queue — no more manual "
                "spreadsheet upkeep."
            ),
        },
    },
}


def agentic_chat_drip_email(
    name: str, step: int, frontend_url: str, role: str | None = None,
) -> tuple[str, str]:
    """5-step drip series introducing the agentic chat. step is 1-indexed.

    If `role` is a known segment, role-specific copy overrides apply to the step.
    """
    idx = max(1, min(step, len(_AGENTIC_DRIP_STEPS))) - 1
    s = dict(_AGENTIC_DRIP_STEPS[idx])
    if role:
        override = _ROLE_OVERRIDES.get(role, {}).get(idx)
        if override:
            s.update(override)
    html = f"""<!DOCTYPE html><html><head>{_BASE_STYLE}</head><body>
    <div class="container"><div class="card">
      <div class="logo">Vandalizer</div>
      <h1>{s['heading']}</h1>
      <p>Hi {name} —</p>
      <p>{s['body']}</p>
      <p style="margin-top:24px"><a class="btn" href="{frontend_url}/">{s['cta']}</a></p>
      <p style="font-size:13px;color:#6b7280;margin-top:16px">
        Step {idx + 1} of {len(_AGENTIC_DRIP_STEPS)} &middot; Reply to this email if you get stuck, or open the Certification panel for the full walkthrough.
      </p>
      <div class="footer">Vandalizer 5.0</div>
    </div></div></body></html>"""
    return s["subject"], html


# ---------------------------------------------------------------------------
# Certification completion email
# ---------------------------------------------------------------------------


def powerup_milestone_email(name: str, workflow_count: int, frontend_url: str) -> tuple[str, str]:
    """Upsell email fired when a user crosses the 30-workflow milestone via chat."""
    subject = f"You've run {workflow_count} workflows from chat — ready to go deeper?"
    html = f"""<!DOCTYPE html><html><head>{_BASE_STYLE}</head><body>
    <div class="container"><div class="card">
      <div class="logo">Vandalizer</div>
      <h1>You\'ve clearly found your flow, {name}.</h1>
      <p>You\'ve driven <span class="highlight">{workflow_count}+ workflows</span> from chat. That puts you in power-user territory — here\'s what you can do next:</p>
      <ul style="padding-left:20px;margin:16px 0;color:#d1d5db">
        <li style="margin-bottom:8px">Promote your most-used extractions into <strong style="color:#fff">validated templates</strong> with test cases. Every teammate who uses them gets the same quality signals you see.</li>
        <li style="margin-bottom:8px">Build a <strong style="color:#fff">team knowledge base</strong> from your OSP handbook so the agent can cite the right policy for every question.</li>
        <li style="margin-bottom:8px">Finish the <strong style="color:#fff">Workflow Architect certification</strong> — the advanced modules cover multi-step orchestration and governance.</li>
      </ul>
      <p style="margin-top:24px"><a class="btn" href="{frontend_url}/">Open Vandalizer</a></p>
      <div class="footer">Vandalizer 5.0 &middot; Power user tips</div>
    </div></div></body></html>"""
    return subject, html


def certification_complete_email(name: str, frontend_url: str) -> tuple[str, str]:
    """Celebration email sent when a user finishes all 11 certification modules."""
    subject = "You're a Certified Vandal Workflow Architect"
    html = f"""<!DOCTYPE html><html><head>{_BASE_STYLE}</head><body>
    <div class="container"><div class="card">
      <div class="logo">Vandalizer</div>
      <h1>Certified. Nice work, {name}.</h1>
      <p>You finished all 11 modules of the Vandal Workflow Architect certification. That's 1,600 XP across AI literacy, workflow design, extraction, validation, and governance.</p>
      <p>Your <strong style="color:#fff">Certified</strong> badge is now visible on every workflow you publish, so your team knows those pipelines were built by someone who understands the full trust stack.</p>
      <p style="margin-top:24px"><a class="btn" href="{frontend_url}/certification">View Your Certification</a></p>
      <p style="font-size:13px;color:#6b7280;margin-top:16px">
        Want to help a colleague get certified? Invite them to your team and they can start the journey with the same verified modules you did.
      </p>
      <div class="footer">Vandalizer &middot; Certified Workflow Architect</div>
    </div></div></body></html>"""
    return subject, html
