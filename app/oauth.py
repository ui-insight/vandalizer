"""OAuth helpers for configuring Azure via Flask-Dance using DB settings."""

from __future__ import annotations

from flask import Flask, current_app
from flask_dance.consumer import oauth_authorized, oauth_error
from flask_dance.contrib.azure import make_azure_blueprint
from flask_login import login_user

from app.utilities.config import get_auth_methods, get_oauth_provider_by_type

azure_blueprint = None

# Microsoft Graph scopes needed for M365 integration (beyond basic login).
# These are requested via the separate /office/connect consent flow.
GRAPH_INTEGRATION_SCOPES = [
    "Mail.Read",
    "Mail.Read.Shared",
    "Files.ReadWrite.All",
    "ChannelMessage.Send",
    "offline_access",
]


def azure_logged_in(blueprint, token):
    """Creates or loads a user after successful Azure login."""
    from flask import redirect, url_for, session
    from app.models import User

    current_app.logger.info(f"azure_logged_in signal received. Token present: {bool(token)}")

    if not token:
        current_app.logger.warning("Failed to fetch token from Azure.")
        # Return False to stop Flask-Dance's default redirect behavior
        return False

    resp = blueprint.session.get("/v1.0/me")
    if not resp.ok:
        current_app.logger.warning(
            f"Failed to fetch user info from Azure Graph: {resp.text}"
        )
        return False

    info = resp.json()
    user_principal_name = info.get("userPrincipalName")

    user = User.objects(user_id=user_principal_name).first()

    if not user:
        email = info.get("mail") or user_principal_name
        user = User(
            user_id=user_principal_name, email=email, name=info["displayName"]
        ).save()
    else:
        if not user.email:
            user.email = info.get("mail") or user_principal_name
        if not user.name:
            user.name = info["displayName"]
        user.save()

    # Make session permanent so Flask-Login session persists
    session.permanent = True
    login_user(user)
    current_app.logger.info(f"User {user_principal_name} logged in via Azure OAuth")

    # Return False to tell Flask-Dance we've handled the login ourselves.
    # This prevents Flask-Dance from storing the token and triggering its
    # default redirect behavior, which can cause infinite loops.
    return False


def azure_error_handler(blueprint, message, response):
    """Handle OAuth errors to prevent infinite redirect loops."""
    current_app.logger.error(f"Azure OAuth error: {message}")
    if response:
        current_app.logger.error(f"OAuth error response: {response}")
    from flask import flash
    flash(f"OAuth login failed: {message}", "danger")
    # Return False to let Flask-Dance handle the error redirect
    return False


def _connect_azure_signal(blueprint):
    """Ensure the oauth_authorized signal is connected once."""
    if getattr(blueprint, "_oauth_signal_connected", False):
        return
    oauth_authorized.connect(azure_logged_in, blueprint)
    oauth_error.connect(azure_error_handler, blueprint)
    blueprint._oauth_signal_connected = True


def configure_azure_blueprint(app: Flask, force: bool = False):
    """Ensure Azure OAuth blueprint is registered using DB config if available.

    Blueprint registration must happen before the first request is handled; if we
    miss that window we mark a flag so the UI can prompt for a restart.
    """
    global azure_blueprint

    try:
        oauth_enabled_now = "oauth" in get_auth_methods()
        app.logger.info(f"configure_azure_blueprint called. oauth_enabled: {oauth_enabled_now}")
    except Exception as e:
        oauth_enabled_now = app.config.get("AUTH_OAUTH_ENABLED", False)
        app.logger.warning(f"Failed to get auth methods from DB, using config: {oauth_enabled_now}. Error: {e}")

    if not oauth_enabled_now:
        app.logger.info("OAuth not enabled, skipping Azure blueprint")
        return None

    if "azure" in app.blueprints and not force:
        app.logger.info("Azure blueprint already registered, connecting signals")
        azure_blueprint = app.blueprints["azure"]
        _connect_azure_signal(azure_blueprint)
        return azure_blueprint

    try:
        azure_config = get_oauth_provider_by_type("azure")
        if azure_config and not azure_config.get("enabled", True):
            app.logger.info("Azure OAuth provider found but is disabled")
            return None

        blueprint = None
        if azure_config:
            client_id = azure_config.get("client_id")
            client_secret = azure_config.get("client_secret")
            tenant = azure_config.get("tenant_id") or azure_config.get("tenant")
            if not client_id or not client_secret or not tenant:
                app.logger.error(
                    f"Azure config incomplete - client_id: {bool(client_id)}, client_secret: {bool(client_secret)}, tenant: {bool(tenant)}"
                )
                return None
            blueprint = make_azure_blueprint(
                client_id=client_id,
                client_secret=client_secret,
                tenant=tenant,
                # redirect_to expects an endpoint; redirect_url is a *post-login* URL.
                # Do not pass the OAuth callback URL here (that causes redirect loops).
                redirect_to="home.index",
            )
            app.logger.info("Azure blueprint configured from database")
        else:
            client_id = app.config.get("CLIENT_ID")
            client_secret = app.config.get("CLIENT_SECRET")
            tenant = app.config.get("TENANT_NAME")

            if client_id and client_secret and tenant:
                blueprint = make_azure_blueprint(
                    client_id=client_id,
                    client_secret=client_secret,
                    tenant=tenant,
                    # redirect_to expects an endpoint; redirect_url is a *post-login* URL.
                    # Do not pass the OAuth callback URL here (that causes redirect loops).
                    redirect_to="home.index",
                )
                app.logger.info("Azure blueprint configured from app config")
            else:
                app.logger.warning(
                    "OAuth enabled but Azure config not found in database or app config"
                )
                return None

        if "azure" not in app.blueprints:
            app.register_blueprint(blueprint, url_prefix="/login")
            
            # Exempt from rate limiting if limiter is configured
            if "limiter" in app.extensions:
                app.extensions["limiter"].exempt(blueprint)
                
            app.logger.info("Azure blueprint registered successfully")

        azure_blueprint = blueprint
        _connect_azure_signal(blueprint)
        return blueprint
    except Exception as e:
        app.logger.error(
            f"OAuth enabled but Azure blueprint could not be registered: {e}"
        )
        import traceback

        app.logger.error(traceback.format_exc())
        return None


# ---------------------------------------------------------------------------
# Graph Integration Consent Flow  (separate from login)
# ---------------------------------------------------------------------------
# This creates a second OAuth blueprint at /office/connect that requests the
# expanded Graph scopes needed for M365 integration.  Users who don't use
# M365 features never see these permission prompts.
# ---------------------------------------------------------------------------

_graph_blueprint = None


def _graph_consent_logged_in(blueprint, token):
    """Handle the return from the Graph consent flow."""
    from flask import redirect, url_for
    from flask_login import current_user as cu

    if not token:
        current_app.logger.warning("Graph consent flow returned no token.")
        return False

    # Store the token with expanded scopes
    from app.utilities.graph_token_store import store_token

    user_id = cu.get_id() if cu and cu.is_authenticated else None
    if not user_id:
        # Fallback: fetch from Graph
        resp = blueprint.session.get("/v1.0/me")
        if resp.ok:
            user_id = resp.json().get("userPrincipalName")

    if user_id:
        store_token(user_id, token)

        # Mark user as M365-enabled
        from app.models import User
        import datetime

        user = User.objects(user_id=user_id).first()
        if user:
            user.m365_enabled = True
            user.m365_connected_at = datetime.datetime.utcnow()
            user.save()

        current_app.logger.info(f"Graph tokens stored for {user_id}")

    # Prevent Flask-Dance from storing the token itself
    return False


def _graph_consent_error(blueprint, message, response):
    """Handle errors during Graph consent flow."""
    current_app.logger.error(f"Graph consent OAuth error: {message}")
    from flask import flash

    flash(f"M365 connection failed: {message}", "danger")
    return False


def configure_graph_consent_blueprint(app: Flask):
    """Register a separate Azure OAuth blueprint for Graph consent.

    This blueprint lives at ``/office/connect`` and requests the expanded
    scopes listed in ``GRAPH_INTEGRATION_SCOPES``.  It is only registered
    when Azure OAuth is configured.
    """
    global _graph_blueprint

    if _graph_blueprint and "azure_graph" in app.blueprints:
        return _graph_blueprint

    # Reuse the same Azure AD app credentials
    azure_config = get_oauth_provider_by_type("azure")
    client_id = client_secret = tenant = None

    if azure_config:
        client_id = azure_config.get("client_id")
        client_secret = azure_config.get("client_secret")
        tenant = azure_config.get("tenant_id") or azure_config.get("tenant")
    else:
        client_id = app.config.get("CLIENT_ID")
        client_secret = app.config.get("CLIENT_SECRET")
        tenant = app.config.get("TENANT_NAME")

    if not (client_id and client_secret and tenant):
        app.logger.info("Azure config not available — skipping Graph consent blueprint")
        return None

    try:
        bp = make_azure_blueprint(
            client_id=client_id,
            client_secret=client_secret,
            tenant=tenant,
            scope=" ".join(GRAPH_INTEGRATION_SCOPES),
            redirect_to="office.dashboard",
            login_url="/graph-connect",
            authorized_url="/graph-connect/authorized",
        )
        # Give it a unique name so it doesn't collide with the login blueprint
        bp.name = "azure_graph"

        if "azure_graph" not in app.blueprints:
            app.register_blueprint(bp, url_prefix="/office/connect")
            if "limiter" in app.extensions:
                app.extensions["limiter"].exempt(bp)

        oauth_authorized.connect(_graph_consent_logged_in, bp)
        oauth_error.connect(_graph_consent_error, bp)

        _graph_blueprint = bp
        app.logger.info("Graph consent blueprint registered at /office/connect")
        return bp
    except Exception as e:
        app.logger.error(f"Failed to register Graph consent blueprint: {e}")
        return None
