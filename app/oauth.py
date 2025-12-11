"""OAuth helpers for configuring Azure via Flask-Dance using DB settings."""

from __future__ import annotations

from flask import Flask, current_app
from flask_dance.consumer import oauth_authorized
from flask_dance.contrib.azure import make_azure_blueprint
from flask_login import login_user

from app.utilities.config import get_auth_methods, get_oauth_provider_by_type

azure_blueprint = None


def azure_logged_in(blueprint, token):
    """Creates or loads a user after successful Azure login."""
    if not token:
        current_app.logger.warning("Failed to fetch token from Azure.")
        return

    resp = blueprint.session.get("/v1.0/me")
    if not resp.ok:
        current_app.logger.warning(
            f"Failed to fetch user info from Azure Graph: {resp.text}"
        )
        return

    info = resp.json()
    user_principal_name = info.get("userPrincipalName")

    # Import here to avoid circular import at module load
    from app.models import User

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

    login_user(user)


def _connect_azure_signal(blueprint):
    """Ensure the oauth_authorized signal is connected once."""
    if getattr(blueprint, "_oauth_signal_connected", False):
        return
    oauth_authorized.connect(azure_logged_in, blueprint)
    blueprint._oauth_signal_connected = True


def configure_azure_blueprint(app: Flask, force: bool = False):
    """Ensure Azure OAuth blueprint is registered using DB config if available.

    Blueprint registration must happen before the first request is handled; if we
    miss that window we mark a flag so the UI can prompt for a restart.
    """
    global azure_blueprint

    try:
        oauth_enabled_now = "oauth" in get_auth_methods()
    except Exception:
        oauth_enabled_now = app.config.get("AUTH_OAUTH_ENABLED", False)

    if not oauth_enabled_now:
        return None

    # If we've already served a request, don't attempt to register new blueprints.
    if getattr(app, "_got_first_request", False) and "azure" not in app.blueprints:
        app.logger.warning(
            "Azure OAuth blueprint not registered before first request; restart required after updating config."
        )
        app.config["AZURE_BLUEPRINT_SKIPPED"] = True
        return None

    if "azure" in app.blueprints and not force:
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
            redirect_url = azure_config.get("redirect_uri")

            if not client_id or not client_secret or not tenant:
                app.logger.error(
                    f"Azure config incomplete - client_id: {bool(client_id)}, client_secret: {bool(client_secret)}, tenant: {bool(tenant)}"
                )
                return None
            blueprint = make_azure_blueprint(
                client_id=client_id,
                client_secret=client_secret,
                tenant=tenant,
                redirect_url=redirect_url or None,
            )
            app.logger.info("Azure blueprint configured from database")
        else:
            client_id = app.config.get("CLIENT_ID")
            client_secret = app.config.get("CLIENT_SECRET")
            tenant = app.config.get("TENANT_NAME")
            redirect_url = app.config.get("AZURE_REDIRECT_URI")

            if client_id and client_secret and tenant:
                blueprint = make_azure_blueprint(
                    client_id=client_id,
                    client_secret=client_secret,
                    tenant=tenant,
                    redirect_url=redirect_url or None,
                )
                app.logger.info("Azure blueprint configured from app config")
            else:
                app.logger.warning(
                    "OAuth enabled but Azure config not found in database or app config"
                )
                return None

        if "azure" not in app.blueprints:
            app.register_blueprint(blueprint, url_prefix="/login")
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
