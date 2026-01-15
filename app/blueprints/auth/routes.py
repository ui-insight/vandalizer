"""Handles authorization routing."""

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask.typing import ResponseReturnValue
from flask_dance.contrib.azure import azure
from flask_login import login_user
from mongoengine.errors import NotUniqueError

from app import load_user
from app.oauth import configure_azure_blueprint
from app.models import TeamInvite, TeamMembership, User
from app.utilities.config import get_auth_methods, get_oauth_provider_by_type

auth = Blueprint("auth", __name__)


@auth.route("/")
def index() -> ResponseReturnValue:
    """Render the landing page if not authorized."""
    # debug("Not authorized")
    user = load_user()
    if user is not None:
        return redirect(url_for("home.index"))

    methods = get_auth_methods()
    oauth_enabled = "oauth" in methods
    registered_blueprint = None
    if oauth_enabled:
        registered_blueprint = configure_azure_blueprint(current_app)

    azure_provider = get_oauth_provider_by_type("azure") if oauth_enabled else None
    azure_missing_fields: list[str] = []
    azure_config_complete = False
    if azure_provider:
        if not azure_provider.get("client_id"):
            azure_missing_fields.append("client_id")
        if not azure_provider.get("client_secret"):
            azure_missing_fields.append("client_secret")
        if not (azure_provider.get("tenant_id") or azure_provider.get("tenant")):
            azure_missing_fields.append("tenant_id")
        azure_config_complete = not azure_missing_fields

    azure_blueprint_registered = registered_blueprint is not None or "azure" in current_app.blueprints
    azure_enabled = (
        oauth_enabled
        and azure_provider is not None
        and azure_config_complete
        and azure_blueprint_registered
    )
    azure_disabled_reason = None
    if oauth_enabled and azure_provider and not azure_enabled:
        if not azure_config_complete:
            azure_disabled_reason = f"Azure config missing: {', '.join(azure_missing_fields)}."
        elif current_app.config.get("AZURE_BLUEPRINT_SKIPPED"):
            azure_disabled_reason = "Azure sign-in is configured but the OAuth blueprint was not registered before first request. Restart the server to apply changes."
        elif not azure_blueprint_registered:
            azure_disabled_reason = "Azure sign-in is configured but the Azure OAuth blueprint is not active."

    return render_template(
        "landing.html",
        AUTH_MODE=current_app.config["AUTH_MODE"],
        password_enabled="password" in methods,
        oauth_enabled="oauth" in methods,
        azure_configured=azure_provider is not None,
        azure_label=(azure_provider or {}).get("display_name", "Sign in with Azure"),
        azure_enabled=azure_enabled,
        azure_missing_fields=azure_missing_fields,
        azure_config_complete=azure_config_complete,
        azure_blueprint_registered=azure_blueprint_registered,
        azure_disabled_reason=azure_disabled_reason,
    )


@auth.route("/login", methods=["GET", "POST"])
def login() -> ResponseReturnValue:
    """Handle the login process. Redirect to Azure login if not authorized."""
    if load_user():
        return redirect(url_for("home.index"))

    methods = get_auth_methods()
    password_enabled = "password" in methods
    oauth_enabled = "oauth" in methods
    azure_available = False
    if oauth_enabled:
        azure_available = configure_azure_blueprint(current_app) is not None or "azure" in current_app.blueprints
    provider = request.args.get("provider")

    if request.method == "GET":
        if provider == "azure" and oauth_enabled:
            if azure_available:
                return redirect(url_for("azure.login"))
            flash("OAuth is enabled but no provider is configured.", "danger")
            return redirect(url_for("auth.index"))

        if oauth_enabled and not password_enabled:
            if azure_available:
                return redirect(url_for("azure.login"))
            flash("OAuth is enabled but no provider is configured.", "danger")
            return redirect(url_for("auth.index"))
        return redirect(url_for("auth.index"))

    if password_enabled:
        email = request.form.get("email")
        password = request.form.get("password")

        user = User.objects(user_id=email).first()

        # Check that user exists and password is correct
        if user and user.check_password(password):
            login_user(user)
            flash("You have been logged in!", "success")
            return redirect(url_for("home.index"))  # Or your main app page
        else:
            flash("Invalid email or password.", "danger")
            return redirect(url_for("auth.index"))

    if oauth_enabled:
        if "azure" not in current_app.blueprints:
            flash("OAuth is enabled but no provider is configured.", "danger")
            return redirect(url_for("auth.index"))
        if not azure.authorized:
            return redirect(url_for("azure.login"))
        return redirect(url_for("home.index"))

    flash("No authentication methods are enabled. Contact an administrator.", "danger")
    return redirect(url_for("auth.index"))


@auth.route("/register", methods=["GET", "POST"])
def register():
    """Handles user registration."""
    if "password" not in get_auth_methods():
        flash("Password registration is disabled. Please use the configured SSO provider.", "warning")
        return redirect(url_for("auth.index"))
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip()
        password = request.form.get("password")

        # Check if user already exists
        if User.objects(user_id=email).first():
            flash("An account with that email already exists.", "warning")
            return redirect(url_for("auth.register"))

        # Create new user
        new_user = User(user_id=email, email=email, name=name)
        new_user.set_password(password)

        # Check for pending invites BEFORE saving the user
        # This prevents the pre_save hook from creating a personal team
        # Normalize email to lowercase since invites are stored lowercased
        pending_invites = list(TeamInvite.objects(email=email.lower(), accepted=False))

        first_invited_team = None
        if pending_invites:
            # Set the current_team before first save to prevent personal team creation
            first_invited_team = pending_invites[0].team
            new_user.current_team = first_invited_team

        # Now save the user (with current_team set if there are invites)
        new_user.save()

        # Process the invites: create memberships and mark as accepted
        for inv in pending_invites:
            # Create membership if not already present (unique index will also protect us)
            try:
                existing = TeamMembership.objects(
                    team=inv.team, user_id=new_user.user_id
                ).first()
                if not existing:
                    TeamMembership(
                        team=inv.team,
                        user_id=new_user.user_id,
                        role=inv.role,
                    ).save()
                # mark invite as accepted
                inv.accepted = True
                inv.save()
            except NotUniqueError:
                # Membership already exists due to race/duplicate; still mark invite accepted.
                inv.accepted = True
                inv.save()

        # Log the user in automatically
        login_user(new_user)

        flash("Account created successfully!", "success")
        return redirect(url_for("home.index"))

    # For GET requests, show the registration form
    return render_template("users/register.html")


@auth.route("/logout")
def logout() -> ResponseReturnValue:
    """Handle the logout process. Clear the session and redirect to the landing page."""
    session.clear()
    return redirect(url_for("auth.index"))


@auth.route("/build_admin")
def build_admin() -> ResponseReturnValue:
    """Build an admin user for development purposes."""
    user = User(user_id="admin", is_admin=True)
    user.save()
    session["user_id"] = "admin"


@auth.route("/login/saml")
def saml_login():
    """Initiate SAML authentication."""
    from onelogin.saml2.auth import OneLogin_Saml2_Auth
    from app.utilities.saml_utils import get_saml_config, prepare_flask_request

    saml_config = get_saml_config()
    if not saml_config:
        flash("SAML is not configured.", "danger")
        return redirect(url_for("auth.index"))

    req = prepare_flask_request(request)
    auth = OneLogin_Saml2_Auth(req, saml_config)

    # Redirect to the IdP
    # return_to is where we go after successful ACS processing
    return redirect(auth.login(return_to=url_for("home.index")))


@auth.route("/login/saml/authorized", methods=["POST"])
def saml_authorized():
    """Receive the SAML response (ACS)."""
    from onelogin.saml2.auth import OneLogin_Saml2_Auth
    from onelogin.saml2.utils import OneLogin_Saml2_Utils
    from app.utilities.saml_utils import get_saml_config, prepare_flask_request

    saml_config = get_saml_config()
    if not saml_config:
        flash("SAML configuration error.", "danger")
        return redirect(url_for("auth.index"))

    req = prepare_flask_request(request)
    auth = OneLogin_Saml2_Auth(req, saml_config)

    auth.process_response()
    errors = auth.get_errors()

    if errors:
        current_app.logger.error(f"SAML Errors: {errors}")
        flash(f"An error occurred during SAML login: {', '.join(errors)}", "danger")
        if current_app.debug:
             flash(auth.get_last_error_reason(), "warning")
        return redirect(url_for("auth.index"))

    if not auth.is_authenticated():
        flash("SAML authentication failed.", "danger")
        return redirect(url_for("auth.index"))

    # Extract user info
    attributes = auth.get_attributes()
    # NameID is usually the unique identifier
    name_id = auth.get_nameid()
    
    # Try to map attributes to typical fields.
    # Note: Attribute names depend on the IdP (e.g., URNs or simple names).
    # You might need to adjust these keys based on your specific IdP.
    email = name_id  # Fallback
    if "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress" in attributes:
        email = attributes["http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress"][0]
    elif "email" in attributes:
        email = attributes["email"][0]
    elif "mail" in attributes:
        email = attributes["mail"][0]
        
    display_name = email.split("@")[0]
    if "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name" in attributes:
        display_name = attributes["http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name"][0]
    elif "name" in attributes:
        display_name = attributes["name"][0]
    elif "displayName" in attributes:
        display_name = attributes["displayName"][0]

    # Login or create user
    user = User.objects(user_id=email).first()
    if not user:
        user = User(
            user_id=email,
            email=email,
            name=display_name
        ).save()
    else:
        # Update details potentially
        if not user.email:
            user.email = email
            user.save()
            
    login_user(user)
    
    # Handle 'RelayState' or default to home
    self_url = OneLogin_Saml2_Utils.get_self_url(req)
    if "RelayState" in request.form and self_url != request.form["RelayState"]:
        return redirect(auth.redirect_to(request.form["RelayState"]))
        
    return redirect(url_for("home.index"))


@auth.route("/saml/metadata")
def saml_metadata():
    """Expose SP metadata XML."""
    from flask import make_response
    from onelogin.saml2.auth import OneLogin_Saml2_Auth
    from app.utilities.saml_utils import get_saml_config, prepare_flask_request

    saml_config = get_saml_config()
    if not saml_config:
        return "SAML not configured", 404

    req = prepare_flask_request(request)
    auth = OneLogin_Saml2_Auth(req, saml_config)
    settings = auth.get_settings()
    metadata = settings.get_sp_metadata()
    errors = settings.validate_metadata(metadata)

    if len(errors) == 0:
        resp = make_response(metadata, 200)
        resp.headers["Content-Type"] = "text/xml"
        return resp
    else:
        return ", ".join(errors), 500

