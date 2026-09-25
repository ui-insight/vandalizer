import datetime
import uuid

from app.models.user import User
from app.models.team import Team, TeamMembership
from app.utils.security import hash_password, verify_password


async def _stamp_login(user: User) -> None:
    """Record login timestamp and initialize onboarding drip for new users."""
    now = datetime.datetime.now(datetime.timezone.utc)
    is_first_login = user.last_login_at is None
    user.last_login_at = now

    # Start onboarding drip for new users on first login
    if is_first_login and user.onboarding_drip_step == 0:
        user.onboarding_drip_next_at = now  # eligible immediately for step 1
        user.email_preferences = user.email_preferences or {}
        user.email_preferences.setdefault("onboarding", True)
        user.email_preferences.setdefault("nudges", True)

    await user.save()


async def _auto_join_default_team(user: User, *, set_current: bool = True) -> None:
    """If a default team is configured in SystemConfig, silently add the user
    as a member if they aren't already.

    set_current=True  → also switch user.current_team (used on first registration).
    set_current=False → just ensure membership exists; don't override their
                        chosen current_team (used on subsequent logins).
    """
    from app.models.system_config import SystemConfig

    cfg = await SystemConfig.get_config()
    if not cfg.default_team_id:
        return

    team = await Team.find_one(Team.uuid == cfg.default_team_id)
    if not team:
        return

    existing = await TeamMembership.find_one(
        TeamMembership.team == team.id,
        TeamMembership.user_id == user.user_id,
    )
    if not existing:
        membership = TeamMembership(team=team.id, user_id=user.user_id, role="member")
        await membership.insert()
        if set_current:
            user.current_team = team.id
            await user.save()


async def _audit_email_sync(user: User, new_email: str, *, provider: str) -> None:
    """Record that an SSO login overwrote a diverged email with the IdP's value,
    so the audit trail explains any earlier user.email_changed entry that no
    longer matches the account."""
    from app.services import audit_service

    await audit_service.log_event(
        action="user.email_synced_from_provider",
        actor_user_id=user.user_id,
        resource_type="user",
        resource_id=user.user_id,
        detail={
            "old_email": user.email,
            "new_email": new_email,
            "provider": provider,
        },
    )


class JitProvisioningDisabled(Exception):
    """SSO asserted an identity with no existing account while the provider
    has just-in-time provisioning turned off."""


# Reason codes returned by authenticate_with_reason on failure. These are
# consumed by the login route to produce a helpful error message.
AUTH_REASON_UNKNOWN_USER = "unknown_user"
AUTH_REASON_SSO_ONLY = "sso_only"
AUTH_REASON_WRONG_PASSWORD = "wrong_password"
AUTH_REASON_TRIAL_EXPIRED = "trial_expired"


async def authenticate_with_reason(
    user_id: str, password: str
) -> tuple[User | None, str | None]:
    """Authenticate and report *why* it failed.

    Returns (user, None) on success, or (None, reason) where reason is one of
    the AUTH_REASON_* constants above.
    """
    # Normalize to lowercase to match Flask's normalize_identity behavior
    normalized = user_id.strip().lower()
    user = await User.find_one(User.user_id == normalized)
    if not user:
        user = await User.find_one(User.email == normalized)
    if not user:
        return None, AUTH_REASON_UNKNOWN_USER
    if not user.password_hash:
        return None, AUTH_REASON_SSO_ONLY
    # A locked trial isn't an auth failure the user can fix by guessing harder,
    # so surface it regardless of password correctness. We return the user (not
    # None) so the login route can route them to the trial-end screen instead of
    # a dead-end 401. The locked account never receives a real session token.
    if user.is_demo_user and user.demo_status == "locked":
        return user, AUTH_REASON_TRIAL_EXPIRED
    if not verify_password(password, user.password_hash):
        return None, AUTH_REASON_WRONG_PASSWORD
    # Silently backfill default-team membership for non-demo users
    if not user.is_demo_user:
        await _auto_join_default_team(user, set_current=False)
    from app.services.team_service import ensure_current_team
    await ensure_current_team(user)
    await _stamp_login(user)
    return user, None


async def authenticate(user_id: str, password: str) -> User | None:
    user, reason = await authenticate_with_reason(user_id, password)
    # Only a clean success (reason is None) counts as authenticated; a locked
    # trial now returns the user alongside a reason, which is not a valid login.
    return user if reason is None else None


async def resolve_oauth_user(
    user_principal_name: str,
    email: str | None,
    display_name: str | None,
    *,
    jit_provisioning: bool = True,
) -> User:
    """Find or create a user from OAuth claims.

    Lookup priority: user_id == upn, then email == mail, then user_id == mail.
    If not found, creates an OAuth-only user (password_hash=None) with a
    personal team — unless the provider has jit_provisioning turned off, in
    which case JitProvisioningDisabled is raised. Existing users are always
    allowed; the flag gates account creation only.
    """
    user = await User.find_one(User.user_id == user_principal_name)
    if not user and email:
        user = await User.find_one(User.email == email)
    if not user and email:
        user = await User.find_one(User.user_id == email)

    if user:
        # Update name/email if changed
        changed = False
        if display_name and user.name != display_name:
            user.name = display_name
            changed = True
        if email and user.email != email:
            await _audit_email_sync(user, email, provider="oauth")
            user.email = email
            changed = True
        if user.sso_provider != "oauth":
            user.sso_provider = "oauth"
            changed = True
        # The IdP asserts this address, so SSO users are verified by arrival
        # and are never asked to confirm (see trial_budget.check_*).
        if not user.email_verified:
            user.email_verified = True
            changed = True
        if changed:
            await user.save()
        # Silently backfill default-team membership for pre-existing users
        await _auto_join_default_team(user, set_current=False)
        from app.services.team_service import ensure_current_team
        await ensure_current_team(user)
        await _stamp_login(user)
        return user

    if not jit_provisioning:
        raise JitProvisioningDisabled(user_principal_name)

    # Create new OAuth-only user
    uid = user_principal_name
    user = User(
        user_id=uid,
        email=email or uid,
        password_hash=None,
        name=display_name or uid,
        sso_provider="oauth",
        email_verified=True,
    )
    await user.insert()

    # Create team + membership with cleanup on failure to avoid orphaned users
    try:
        team_uuid = uuid.uuid4().hex
        team = Team(
            uuid=team_uuid,
            name=f"{display_name or uid}'s Team",
            owner_user_id=uid,
        )
        await team.insert()

        membership = TeamMembership(
            team=team.id,
            user_id=uid,
            role="owner",
        )
        await membership.insert()

        user.current_team = team.id
        await user.save()
    except Exception:
        await user.delete()
        raise

    await _auto_join_default_team(user, set_current=True)
    await _stamp_login(user)
    return user


async def resolve_saml_user(
    uid: str,
    email: str | None,
    display_name: str | None,
    department: str | None = None,
    *,
    jit_provisioning: bool = True,
) -> User:
    """Find or create a user from SAML assertion attributes.

    Similar to resolve_oauth_user but also maps department to organization.
    Raises JitProvisioningDisabled instead of creating when the provider has
    just-in-time provisioning turned off; existing users are always allowed.
    """
    user = await User.find_one(User.user_id == uid)
    if not user and email:
        user = await User.find_one(User.email == email)

    if user:
        changed = False
        if display_name and user.name != display_name:
            user.name = display_name
            changed = True
        if email and user.email != email:
            await _audit_email_sync(user, email, provider="saml")
            user.email = email
            changed = True
        if user.sso_provider != "saml":
            user.sso_provider = "saml"
            changed = True
        # The IdP asserts this address, so SSO users are verified by arrival
        # and are never asked to confirm (see trial_budget.check_*).
        if not user.email_verified:
            user.email_verified = True
            changed = True
        # Auto-map org from department if not already set
        if department and not user.organization_id:
            from app.models.organization import Organization
            org = await Organization.find_one(Organization.name == department)
            if org:
                user.organization_id = org.uuid
                changed = True
        if changed:
            await user.save()
        # Silently backfill default-team membership for pre-existing users
        await _auto_join_default_team(user, set_current=False)
        from app.services.team_service import ensure_current_team
        await ensure_current_team(user)
        await _stamp_login(user)
        return user

    if not jit_provisioning:
        raise JitProvisioningDisabled(uid)

    # Create new SAML user
    user = User(
        user_id=uid,
        email=email or uid,
        password_hash=None,
        name=display_name or uid,
        sso_provider="saml",
        email_verified=True,
    )

    # Auto-map organization from department
    if department:
        from app.models.organization import Organization
        org = await Organization.find_one(Organization.name == department)
        if org:
            user.organization_id = org.uuid

    await user.insert()

    try:
        team_uuid = uuid.uuid4().hex
        team = Team(
            uuid=team_uuid,
            name=f"{display_name or uid}'s Team",
            owner_user_id=uid,
            organization_id=user.organization_id,
        )
        await team.insert()

        membership = TeamMembership(
            team=team.id,
            user_id=uid,
            role="owner",
        )
        await membership.insert()

        user.current_team = team.id
        await user.save()
    except Exception:
        await user.delete()
        raise

    await _auto_join_default_team(user, set_current=True)
    await _stamp_login(user)
    return user


async def register(user_id: str, email: str, password: str, name: str | None = None) -> User:
    # Normalize to lowercase to match Flask behavior
    user_id = user_id.strip().lower()
    email = email.strip().lower()

    existing = await User.find_one(User.user_id == user_id)
    if existing:
        raise ValueError("User ID already taken")

    existing_email = await User.find_one(User.email == email)
    if existing_email:
        raise ValueError("Email already registered")

    user = User(
        user_id=user_id,
        email=email,
        password_hash=hash_password(password),
        name=name or user_id,
    )
    await user.insert()

    # Create team + membership with cleanup on failure to avoid orphaned users
    try:
        team_uuid = uuid.uuid4().hex
        team = Team(
            uuid=team_uuid,
            name=f"{name or user_id}'s Team",
            owner_user_id=user_id,
        )
        await team.insert()

        membership = TeamMembership(
            team=team.id,
            user_id=user_id,
            role="owner",
        )
        await membership.insert()

        user.current_team = team.id
        await user.save()
    except Exception:
        # Clean up the user so registration can be retried
        await user.delete()
        raise

    await _auto_join_default_team(user, set_current=True)
    return user
