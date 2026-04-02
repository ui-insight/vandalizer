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
            start_tls=settings.smtp_start_tls,
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
      <p style="margin-top:24px"><a class="btn" href="{frontend_url}/login">Sign In Now</a></p>
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
    subject = f'Verification update: "{item_name}" — {label}'

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
) -> tuple[str, str]:
    """Returns (subject, html_body) when support replies to a user's ticket."""
    subject = f"Re: {ticket_subject}"
    html = f"""<!DOCTYPE html><html><head>{_BASE_STYLE}</head><body>
    <div class="container"><div class="card">
      <div class="logo">Vandalizer Support</div>
      <h1>New reply on your ticket</h1>
      <p>Hi {user_name}, there's a new reply on your support ticket <span class="highlight">{ticket_subject}</span>.</p>
      <div style="margin:16px 0;padding:12px 16px;background:rgba(255,255,255,0.05);border-left:3px solid #f1b300;border-radius:4px;">
        <p style="margin:0;font-size:14px;color:#d1d5db;">{message[:500]}</p>
      </div>
      <p style="margin-top:24px"><a class="btn" href="{frontend_url}/support?ticket={ticket_uuid}">View Ticket</a></p>
      <div class="footer">Vandalizer Support System</div>
    </div></div></body></html>"""
    return subject, html


def support_status_email(
    user_name: str, ticket_subject: str, new_status: str, ticket_uuid: str, frontend_url: str,
) -> tuple[str, str]:
    """Returns (subject, html_body) when a support ticket status changes."""
    subject = f"Ticket {new_status}: {ticket_subject}"
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
) -> tuple[str, str]:
    """Returns (subject, html_body) when a user replies on a support ticket (for agents)."""
    subject = f"New message on ticket: {ticket_subject}"
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
      <p style="margin-top:24px"><a class="btn" href="{frontend_url}/approvals?id={approval_uuid}">Review Now</a></p>
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
            "Your credentials were included in your activation email &mdash; "
            "check your inbox (and spam folder) for an email from us."
        ),
        "cta": "Sign In Now",
    },
    {
        "subject": "Don't miss out — your Vandalizer trial is ticking",
        "heading": "Your trial clock is running",
        "body": (
            "Your 2-week Vandalizer demo is already active, but you haven't "
            "signed in yet. Every day you wait is a day less to explore the platform. "
            "If you're having trouble logging in, just reply to this email and we'll help."
        ),
        "cta": "Log In Now",
    },
    {
        "subject": "Last reminder — your Vandalizer demo expires soon",
        "heading": "Running out of time",
        "body": (
            "This is our last reminder &mdash; your Vandalizer demo trial will expire "
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
        1: "Welcome to Vandalizer — start your certification journey",
        2: f"Ready for hands-on? {module_title} is next",
        3: f"Keep building — {module_title} awaits",
        4: "You're making great progress — keep going!",
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
      <p>These verified extractions and knowledge bases are ready to use in your workflows.</p>
      <p style="margin-top:24px"><a class="btn" href="{frontend_url}/library?tab=catalog">Browse Catalog</a></p>
      <div class="footer">Vandalizer</div>
    </div></div></body></html>"""
    return subject, html
