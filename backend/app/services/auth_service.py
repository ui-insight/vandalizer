import uuid

from app.models.user import User
from app.models.team import Team, TeamMembership
from app.utils.security import hash_password, verify_password


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


async def authenticate(user_id: str, password: str) -> User | None:
    # Normalize to lowercase to match Flask's normalize_identity behavior
    normalized = user_id.strip().lower()
    user = await User.find_one(User.user_id == normalized)
    if not user:
        user = await User.find_one(User.email == normalized)
    if not user or not user.password_hash:
        return None
    if not verify_password(password, user.password_hash):
        return None
    # Silently backfill default-team membership for pre-existing users
    await _auto_join_default_team(user, set_current=False)
    return user


async def resolve_oauth_user(
    user_principal_name: str,
    email: str | None,
    display_name: str | None,
) -> User:
    """Find or create a user from OAuth claims.

    Lookup priority: user_id == upn, then email == mail, then user_id == mail.
    If not found, creates an OAuth-only user (password_hash=None) with a personal team.
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
            user.email = email
            changed = True
        if changed:
            await user.save()
        # Silently backfill default-team membership for pre-existing users
        await _auto_join_default_team(user, set_current=False)
        return user

    # Create new OAuth-only user
    uid = user_principal_name
    user = User(
        user_id=uid,
        email=email or uid,
        password_hash=None,
        name=display_name or uid,
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
    return user


async def resolve_saml_user(
    uid: str,
    email: str | None,
    display_name: str | None,
    department: str | None = None,
) -> User:
    """Find or create a user from SAML assertion attributes.

    Similar to resolve_oauth_user but also maps department to organization.
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
            user.email = email
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
        return user

    # Create new SAML user
    user = User(
        user_id=uid,
        email=email or uid,
        password_hash=None,
        name=display_name or uid,
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
