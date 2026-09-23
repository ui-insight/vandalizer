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


def _prefs_footer(frontend_url: str) -> str:
    """Footer for engagement (non-transactional) emails.

    Every marketing-class email must carry a way off the list; the Account
    page hosts the email-preference toggles.
    """
    return (
        '<div class="footer">Vandalizer &middot; '
        f'<a href="{frontend_url}/account" style="color:#6b7280">Manage email preferences</a></div>'
    )


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


def verify_email_email(
    name: str, magic_link: str, budget_tokens: int | None = None
) -> tuple[str, str]:
    """Returns (subject, html_body) asking a new signup to confirm their address.

    Sent at registration on a trial deployment. Confirming is what unlocks AI
    features — and because the link signs them in, the one click both verifies
    the address and gets them back to the workspace.
    """
    subject = "Confirm your email to start using Vandalizer"
    allowance = (
        f" Your account includes <span class=\"highlight\">{_fmt_tokens(budget_tokens)} AI tokens</span>,"
        " with no time limit."
        if budget_tokens
        else ""
    )
    html = f"""<!DOCTYPE html><html><head>{_BASE_STYLE}</head><body>
    <div class="container"><div class="card">
      <div class="logo">Vandalizer</div>
      <h1>One click and you're in</h1>
      <p>Hi {name}, welcome to Vandalizer. Confirm this email address to switch on
         the AI features — extraction, workflows, and chat over your documents.{allowance}</p>
      <p style="margin-top:24px"><a class="btn" href="{magic_link}">Confirm my email</a></p>
      <p style="font-size:13px;color:#6b7280;margin-top:16px">The link signs you
         in too, so there's nothing else to do. You can browse your workspace
         before confirming; AI features wait until you do.</p>
      <div class="footer">Vandalizer</div>
    </div></div></body></html>"""
    return subject, html


_CODE_STYLE = (
    "font-family:'SF Mono',Monaco,Consolas,'Courier New',monospace;"
    "background:#0a0a0a;color:#fff;padding:3px 8px;border-radius:4px;"
    "border:1px solid rgba(255,255,255,0.15);font-size:14px;"
    "white-space:nowrap;user-select:all;-webkit-user-select:all;letter-spacing:0.5px;"
)


def _fmt_tokens(tokens: int) -> str:
    """'2,000,000' — token counts are big; commas keep them readable."""
    return f"{tokens:,}"


def activation_email(
    name: str,
    user_id: str,
    frontend_url: str,
    magic_link: str | None = None,
    budget_tokens: int | None = None,
) -> tuple[str, str]:
    """Returns (subject, html_body) for demo account activation.

    Passwordless by design: the email leads with a one-click sign-in link rather
    than an emailed password, so there's no credential to mistype, rotate, or
    leak. Users who prefer a password can set one anytime via "Forgot password".
    The trial is token-metered, not timed — the email says what's included.
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
    included = (
        f"""full platform access with <span class="highlight">{_fmt_tokens(budget_tokens)} AI tokens</span> included — no time limit, use them at your own pace"""
        if budget_tokens
        else "full platform access"
    )
    html = f"""<!DOCTYPE html><html><head>{_BASE_STYLE}</head><body>
    <div class="container"><div class="card">
      <div class="logo">Vandalizer</div>
      <h1>Your demo account is active!</h1>
      <p>Hi {name}, great news: your Vandalizer demo account is ready to go. You have {included}.</p>{sign_in_section}
      <p style="font-size:13px;color:#6b7280;margin-top:16px">Your account email is <code style="{_CODE_STYLE}">{user_id}</code>. Prefer to log in with a password? Set one anytime via <a href="{frontend_url}/login" style="color:#f1b300">Forgot password</a>.</p>
      <div class="footer">Vandalizer</div>
    </div></div></body></html>"""
    return subject, html


def budget_warning_email(
    name: str, used: int, budget: int, frontend_url: str
) -> tuple[str, str]:
    """Returns (subject, html_body) for the ~80%-of-budget heads-up.

    The token-metered twin of the old day-12 expiry warning: nothing is about
    to be taken away on a date, so the tone is informational — here's where you
    are, and here's what happens when you get to the end.
    """
    remaining = max(0, budget - used)
    subject = "You've used most of your included Vandalizer tokens"
    html = f"""<!DOCTYPE html><html><head>{_BASE_STYLE}</head><body>
    <div class="container"><div class="card">
      <div class="logo">Vandalizer</div>
      <h1>A heads-up on your token balance</h1>
      <p>Hi {name}, you've used <span class="highlight">{_fmt_tokens(used)}</span> of your
         {_fmt_tokens(budget)} included AI tokens — about
         <span class="highlight">{_fmt_tokens(remaining)}</span> left.</p>
      <p>Nothing expires and there's no deadline. When the balance runs out, your
         workspace stays exactly as it is — documents, extractions, and past
         answers all remain — and we'll send you a one-click top-up link so you
         can keep going.</p>
      <p style="margin-top:24px"><a class="btn" href="{frontend_url}/landing">Back to Vandalizer</a></p>
      <div class="footer">Vandalizer</div>
    </div></div></body></html>"""
    return subject, html


def trial_exhausted_email(name: str, trial_end_url: str) -> tuple[str, str]:
    """Returns (subject, html_body) for the friendly out-of-tokens notification.

    Links to the trial-end screen, where the user can top up (one click for
    light users, a few notes for heavy ones) or tell us what to build next.
    """
    subject = "Your Vandalizer tokens ran out — here's a top-up"
    html = f"""<!DOCTYPE html><html><head>{_BASE_STYLE}</head><body>
    <div class="container"><div class="card">
      <div class="logo">Vandalizer</div>
      <h1>You've used your included tokens — let's get you more</h1>
      <p>Hi {name}, you've worked through the AI tokens included with your
         Vandalizer account. Vandalizer is an evolving beta built for research
         offices, and the feedback from people using it like you are is actively
         shaping where it goes next.</p>
      <p>Your workspace is untouched and still yours to browse — everything you
         uploaded and extracted is right where you left it. To start running AI
         again, grab a top-up below, or tell us what would make Vandalizer more
         useful for your office. Either way, we'll keep you going.</p>
      <p style="margin-top:24px"><a class="btn" href="{trial_end_url}">Top up &amp; share your thoughts</a></p>
      <div class="footer">Vandalizer</div>
    </div></div></body></html>"""
    return subject, html


def trial_topup_email(
    name: str,
    new_budget: int,
    frontend_url: str,
    magic_link: str | None = None,
) -> tuple[str, str]:
    """Returns (subject, html_body) confirming a self-serve token top-up.

    Trial accounts sign in via magic link (their password is random and was
    never disclosed), so the CTA carries one whenever the caller can mint it —
    a bare /login link is a dead end for these users.
    """
    subject = "Your Vandalizer tokens are topped up"
    cta_url = magic_link or f"{frontend_url}/login"
    html = f"""<!DOCTYPE html><html><head>{_BASE_STYLE}</head><body>
    <div class="container"><div class="card">
      <div class="logo">Vandalizer</div>
      <h1>You're back in — welcome!</h1>
      <p>Hi {name}, your Vandalizer account is topped up. Your balance now runs to
         <span class="highlight">{_fmt_tokens(new_budget)} tokens</span> in total.</p>
      <p>Thanks for helping shape the product. As new releases land, you'll see
         them here first.</p>
      <p style="margin-top:24px"><a class="btn" href="{cta_url}">Back to Vandalizer</a></p>
      <p style="font-size:13px;color:#6b7280;margin-top:16px">Prefer a password?
         Set one anytime via <a href="{frontend_url}/login" style="color:#f1b300">Forgot password</a> on the sign-in page.</p>
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


def email_changed_notice(
    name: str, old_email: str, new_email: str,
) -> tuple[str, str]:
    """Returns (subject, html_body) sent to the *old* address after an email change.

    A security heads-up so the original owner notices an unexpected change while
    they may still control the old inbox.
    """
    subject = "Your Vandalizer email address was changed"
    html = f"""<!DOCTYPE html><html><head>{_BASE_STYLE}</head><body>
    <div class="container"><div class="card">
      <div class="logo">Vandalizer</div>
      <h1>Email Address Changed</h1>
      <p>Hi {name}, the email address on your Vandalizer account was just changed from <strong>{old_email}</strong> to <strong>{new_email}</strong>.</p>
      <p style="font-size:13px;color:#6b7280;margin-top:16px">If you made this change, no action is needed. If you did <strong>not</strong> make this change, contact your Vandalizer administrator immediately &mdash; your account may be compromised.</p>
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


def verification_submitted_email(
    reviewer_name: str,
    submitter_name: str,
    item_kind: str,
    item_name: str,
    summary: str | None,
    frontend_url: str,
    request_uuid: str | None = None,
) -> tuple[str, str]:
    """Returns (subject, html_body) telling a reviewer a new submission is queued."""
    kind_label = item_kind.replace("_", " ")
    subject = f'New sharing request: "{item_name}"'
    # Link to the submission, not the queue. A reviewer clicking through
    # otherwise has to find the right row themselves, which is worst at exactly
    # this moment — they have the least context about which item the mail was
    # for — and gets worse as the queue grows. The approval flow already links
    # to /reviews/{uuid}; this is the same idea for verification.
    queue_link = f"{frontend_url}/verification"
    button_label = "Open Queue"
    if request_uuid:
        queue_link = f"{queue_link}?request={request_uuid}"
        button_label = "Open Submission"

    summary_block = ""
    if summary:
        summary_block = f"""
      <div style="margin:16px 0;padding:12px 16px;background:rgba(255,255,255,0.05);border-left:3px solid #f1b300;border-radius:4px;">
        <p style="margin:0;font-size:14px;color:#d1d5db;"><strong style="color:#fff;">Summary:</strong><br/>{summary}</p>
      </div>"""

    html = f"""<!DOCTYPE html><html><head>{_BASE_STYLE}</head><body>
    <div class="container"><div class="card">
      <div class="logo">Vandalizer</div>
      <h1>New submission awaiting review</h1>
      <p>Hi {reviewer_name}, <strong style="color:#fff">{submitter_name}</strong> asked to share the {kind_label} <span class="highlight">{item_name}</span> with everyone.</p>
      {summary_block}
      <p style="margin-top:24px"><a class="btn" href="{queue_link}">{button_label}</a></p>
      <div class="footer">Vandalizer</div>
    </div></div></body></html>"""
    return subject, html


def quality_regression_email(
    owner_name: str,
    item_name: str,
    item_kind_label: str,
    previous_score: float,
    current_score: float,
    item_url: str,
) -> tuple[str, str]:
    """Returns (subject, html_body) telling an owner their item's quality dropped.

    Sent only for ``critical`` regressions. An in-app bell entry is the right
    weight for a warning; a critical drop on something the owner may be about
    to rely on has to reach them where they actually are.
    """
    drop = previous_score - current_score
    subject = f'Quality regression: "{item_name}"'
    html = f"""<!DOCTYPE html><html><head>{_BASE_STYLE}</head><body>
    <div class="container"><div class="card">
      <div class="logo">Vandalizer</div>
      <h1>Quality dropped on "{item_name}"</h1>
      <p>Hi {owner_name}, the automatic revalidation of your {item_kind_label}
      <span class="highlight">{item_name}</span> scored materially lower than it did before.</p>
      <div style="margin:16px 0;padding:12px 16px;background:rgba(255,255,255,0.05);border-left:3px solid #ef4444;border-radius:4px;">
        <p style="margin:0;font-size:14px;color:#d1d5db;">
          <strong style="color:#fff;">{previous_score:.0f}</strong> &rarr;
          <strong style="color:#fff;">{current_score:.0f}</strong>
          &nbsp;({drop:.0f} points)
        </p>
      </div>
      <p>Until someone reviews it, this item shows <strong style="color:#fff">regression pending review</strong>
      instead of its previous quality rating. Re-validating it is the fastest way to find out whether the
      drop is real.</p>
      <p style="margin-top:24px"><a class="btn" href="{item_url}">Open and re-validate</a></p>
      <div class="footer">Vandalizer</div>
    </div></div></body></html>"""
    return subject, html


def verification_status_email(
    submitter_name: str,
    item_name: str,
    new_status: str,
    reviewer_notes: str | None,
    frontend_url: str,
) -> tuple[str, str]:
    """Returns (subject, html_body) for a catalog review status change."""
    status_labels = {
        "approved": ("Accepted", "An examiner checked it over and shared it with everyone here, with its measured score."),
        "rejected": ("Declined", "The examiner decided not to share this one."),
        "returned": ("Sent back", "The examiner sent your submission back with feedback."),
        "in_review": ("Under Review", "An examiner has started reviewing your submission."),
    }
    label, default_body = status_labels.get(new_status, (new_status.title(), ""))
    body_text = reviewer_notes or default_body
    subject = f'Sharing request: "{item_name}" - {label}'

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


# Factual reminders only — no countdowns, scarcity, or "don't miss out"
# framing. The audience is professionals; the sequence is capped at three
# and stops the moment they sign in.
_RECAPTURE_SEQUENCE = [
    {
        "subject": "Your Vandalizer demo account is ready",
        "heading": "Ready when you are",
        "body": (
            "Your Vandalizer demo account was activated, but you haven't "
            "signed in yet. Your credentials were included in your activation "
            "email — check your inbox (and spam folder) for an email from us."
        ),
        "cta": "Sign In",
    },
    {
        "subject": "Need a hand signing in to your Vandalizer demo?",
        "heading": "Your demo is active",
        "body": (
            "Your 2-week Vandalizer demo is active, but you haven't signed in "
            "yet. If the activation email went missing or something isn't "
            "working, just reply to this email and we'll help."
        ),
        "cta": "Sign In",
    },
    {
        "subject": "Your Vandalizer demo expires soon",
        "heading": "Before your demo window closes",
        "body": (
            "A last note — we send at most three of these. Your demo account "
            "will expire soon. If you'd still like a look, the button below "
            "signs you in; if the timing didn't work out, reply to this email "
            "and we'll set you up with a fresh window when you're ready."
        ),
        "cta": "Sign In",
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
      <div class="footer">Vandalizer &middot; We send at most three of these reminders, and they stop as soon as you sign in.</div>
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
        4: f"Your next module: {module_title}",
    }
    subject = subjects.get(step, f"Continue your certification: {module_title}")

    html = f"""<!DOCTYPE html><html><head>{_BASE_STYLE}</head><body>
    <div class="container"><div class="card">
      <div class="logo">Vandalizer</div>
      <h1>{module_title}</h1>
      <p>Hi {name}, {module_description}</p>
      <p style="margin-top:24px"><a class="btn" href="{frontend_url}/certification">Open Certification</a></p>
      <p style="font-size:13px;color:#6b7280;margin-top:16px">Each module is a short, hands-on step toward the Vandal Workflow Architect certification.</p>
      {_prefs_footer(frontend_url)}
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
      <p>These verified extractions and knowledge bases are ready to use in your workflows.</p>
      <p style="margin-top:24px"><a class="btn" href="{frontend_url}/library?tab=catalog">Browse Catalog</a></p>
      {_prefs_footer(frontend_url)}
    </div></div></body></html>"""
    return subject, html
