import datetime
import secrets
import uuid

from beanie import PydanticObjectId

from app.models.folder import SmartFolder
from app.models.team import Team, TeamInvite, TeamMembership
from app.models.user import User

ROLE_RANK = {"owner": 0, "admin": 1, "member": 2}
INVITE_EXPIRY_DAYS = 30


async def get_user_teams(user_id: str) -> list[dict]:
    """Get all teams the user belongs to, with their role."""
    memberships = await TeamMembership.find(
        TeamMembership.user_id == user_id
    ).to_list()
    if not memberships:
        return []

    # Deduplicate: keep only one membership per team (highest-ranked role)
    best: dict[PydanticObjectId, TeamMembership] = {}
    duplicates: list[TeamMembership] = []
    for m in memberships:
        existing = best.get(m.team)
        if existing is None:
            best[m.team] = m
        else:
            # Keep the one with the higher role (lower rank number)
            if ROLE_RANK.get(m.role, 99) < ROLE_RANK.get(existing.role, 99):
                duplicates.append(existing)
                best[m.team] = m
            else:
                duplicates.append(m)
    # Clean up duplicate memberships
    for dup in duplicates:
        await dup.delete()

    # Batch-fetch all teams in one query instead of N+1
    team_ids = list(best.keys())
    teams = await Team.find({"_id": {"$in": team_ids}}).to_list()
    team_map = {team.id: team for team in teams}
    result = []
    for m in best.values():
        team = team_map.get(m.team)
        if team:
            result.append({
                "id": str(team.id),
                "uuid": team.uuid,
                "name": team.name,
                "owner_user_id": team.owner_user_id,
                "role": m.role,
            })
    return result


async def get_team_members(team_id: PydanticObjectId) -> list[dict]:
    """Get all members of a team."""
    memberships = await TeamMembership.find(
        TeamMembership.team == team_id
    ).to_list()
    if not memberships:
        return []
    # Batch-fetch all users in one query instead of N+1
    user_ids = [m.user_id for m in memberships]
    users = await User.find({"user_id": {"$in": user_ids}}).to_list()
    user_map = {u.user_id: u for u in users}
    result = []
    for m in memberships:
        user = user_map.get(m.user_id)
        result.append({
            "user_id": m.user_id,
            "role": m.role,
            "name": user.name if user else None,
            "email": user.email if user else None,
        })
    return result


async def get_team_invites(team_id: PydanticObjectId) -> list[dict]:
    """Get pending invites for a team."""
    invites = await TeamInvite.find(
        TeamInvite.team == team_id,
        TeamInvite.accepted == False,  # noqa: E712
    ).to_list()
    return [
        {
            "id": str(inv.id),
            "email": inv.email,
            "role": inv.role,
            "accepted": inv.accepted,
            "token": inv.token,
            "created_at": inv.created_at.isoformat() if inv.created_at else None,
        }
        for inv in invites
    ]


async def create_team(name: str, user_id: str) -> Team:
    """Create a new team with the user as owner."""
    team = Team(
        uuid=uuid.uuid4().hex,
        name=name,
        owner_user_id=user_id,
    )
    await team.insert()
    membership = TeamMembership(team=team.id, user_id=user_id, role="owner")
    await membership.insert()
    return team


async def update_team_name(
    team_uuid: str, name: str, actor_user_id: str
) -> Team:
    """Rename a team. Actor must be owner or admin."""
    team = await Team.find_one(Team.uuid == team_uuid)
    if not team:
        raise ValueError("Team not found")
    _require_min_role(
        await _get_membership(team.id, actor_user_id), "admin"
    )
    team.name = name
    await team.save()
    return team


async def invite_member(
    team_uuid: str, email: str, role: str, actor_user_id: str,
    settings=None,
) -> TeamInvite:
    """Invite a user to a team by email and send an invitation email."""
    team = await Team.find_one(Team.uuid == team_uuid)
    if not team:
        raise ValueError("Team not found")
    _require_min_role(
        await _get_membership(team.id, actor_user_id), "admin"
    )

    existing = await TeamInvite.find_one(
        TeamInvite.team == team.id,
        TeamInvite.email == email,
    )
    if existing and not existing.accepted:
        existing.role = role
        existing.token = secrets.token_urlsafe(32)
        existing.resend_count += 1
        await existing.save()
        invite = existing
    else:
        invite = TeamInvite(
            team=team.id,
            email=email,
            invited_by_user_id=actor_user_id,
            role=role,
            token=secrets.token_urlsafe(32),
        )
        await invite.insert()

    # Send invitation email
    await _send_invite_email(invite, team, actor_user_id, settings)

    return invite


async def _send_invite_email(
    invite: TeamInvite, team: Team, inviter_user_id: str, settings=None,
) -> None:
    """Send the invitation email."""
    from app.config import Settings
    from app.services.email_service import send_email, team_invite_email

    if settings is None:
        settings = Settings()

    inviter = await User.find_one(User.user_id == inviter_user_id)
    inviter_name = inviter.name if inviter else inviter_user_id

    accept_url = f"{settings.frontend_url}/invite?token={invite.token}"
    subject, html = team_invite_email(inviter_name, team.name, invite.role, accept_url)
    await send_email(invite.email, subject, html, settings)


async def get_invite_info(token: str) -> dict | None:
    """Return metadata about an invite token, or None if missing/expired/accepted.

    Public — used so an unauthenticated invitee can see which team invited them
    before signing up or logging in.
    """
    invite = await TeamInvite.find_one(TeamInvite.token == token)
    if not invite:
        return None
    if invite.accepted:
        return None
    expired = bool(
        invite.created_at
        and (datetime.datetime.now() - invite.created_at).days > INVITE_EXPIRY_DAYS
    )
    team = await Team.get(invite.team)
    inviter = await User.find_one(User.user_id == invite.invited_by_user_id)
    return {
        "email": invite.email,
        "role": invite.role,
        "team_name": team.name if team else "a team",
        "team_uuid": team.uuid if team else None,
        "inviter_name": (inviter.name or inviter.user_id) if inviter else None,
        "expired": expired,
    }


async def accept_invite(token: str, user: User) -> Team:
    """Accept a team invitation."""
    invite = await TeamInvite.find_one(TeamInvite.token == token)
    if not invite:
        raise ValueError("Invalid invite token")

    # Check if invite has expired
    if invite.created_at and (
        datetime.datetime.now() - invite.created_at
    ).days > INVITE_EXPIRY_DAYS:
        raise ValueError("Invite has expired")

    team = await Team.get(invite.team)
    if not team:
        raise ValueError("Team not found")

    # Create membership if not exists
    existing = await TeamMembership.find_one(
        TeamMembership.team == team.id,
        TeamMembership.user_id == user.user_id,
    )
    if not existing:
        membership = TeamMembership(
            team=team.id, user_id=user.user_id, role=invite.role
        )
        await membership.insert()
    elif existing.role != invite.role:
        existing.role = invite.role
        await existing.save()

    was_new_acceptance = not invite.accepted
    invite.accepted = True
    await invite.save()

    user.current_team = team.id
    await user.save()

    # Notify the inviter only the first time — later re-accepts (e.g. a
    # register-then-explicit-accept sequence) must not fire duplicate emails.
    if was_new_acceptance:
        await _notify_invite_accepted(invite, team, user)

    return team


async def _notify_invite_accepted(
    invite: TeamInvite, team: Team, member: User,
) -> None:
    """Notify the inviter when someone joins the team."""
    from app.config import Settings
    from app.services.notification_service import create_notification
    from app.services.email_service import send_email, team_member_joined_email

    if not invite.invited_by_user_id:
        return

    member_name = member.name or member.user_id

    # In-app notification
    await create_notification(
        user_id=invite.invited_by_user_id,
        kind="team_member_joined",
        title=f"{member_name} joined {team.name}",
        body=f"{member_name} accepted your invitation.",
        link="/teams",
    )

    # Email
    inviter = await User.find_one(User.user_id == invite.invited_by_user_id)
    if inviter and inviter.email:
        settings = Settings()
        subject, html = team_member_joined_email(
            inviter_name=inviter.name or inviter.user_id,
            member_name=member_name,
            team_name=team.name,
            frontend_url=settings.frontend_url,
        )
        await send_email(inviter.email, subject, html, settings)


async def switch_team(team_uuid: str, user: User) -> Team:
    """Switch the user's current team."""
    team = await Team.find_one(Team.uuid == team_uuid)
    if not team:
        raise ValueError("Team not found")
    membership = await _get_membership(team.id, user.user_id)
    if not membership:
        raise ValueError("Not a member of this team")
    user.current_team = team.id
    await user.save()
    return team


async def change_role(
    team_uuid: str, target_user_id: str, new_role: str, actor_user_id: str
) -> None:
    """Change a team member's role."""
    team = await Team.find_one(Team.uuid == team_uuid)
    if not team:
        raise ValueError("Team not found")

    actor_m = await _get_membership(team.id, actor_user_id)
    _require_min_role(actor_m, "admin")

    target_m = await _get_membership(team.id, target_user_id)
    if not target_m:
        raise ValueError("Target user is not a member")

    # Only owner can change another owner's role
    if target_m.role == "owner" and actor_m.role != "owner":
        raise ValueError("Only owners can change another owner's role")

    # Owner cannot demote themselves
    if target_user_id == actor_user_id and actor_m.role == "owner":
        raise ValueError("Owner cannot demote themselves")

    target_m.role = new_role
    await target_m.save()


async def remove_member(
    team_uuid: str, target_user_id: str, actor_user_id: str
) -> None:
    """Remove a member from a team.

    Admins/owners can remove other non-owner members.
    Any non-owner member can remove themselves (leave).
    """
    team = await Team.find_one(Team.uuid == team_uuid)
    if not team:
        raise ValueError("Team not found")

    is_self = target_user_id == actor_user_id

    if is_self:
        actor_m = await _get_membership(team.id, actor_user_id)
        if not actor_m:
            raise ValueError("You are not a member of this team")
        if actor_m.role == "owner":
            raise ValueError(
                "Owners cannot leave. Transfer ownership first."
            )
        target_m = actor_m
    else:
        actor_m = await _get_membership(team.id, actor_user_id)
        _require_min_role(actor_m, "admin")
        target_m = await _get_membership(team.id, target_user_id)
        if not target_m:
            raise ValueError("Target user is not a member")
        if target_m.role == "owner":
            raise ValueError("Cannot remove a team owner")

    await target_m.delete()

    # If target's current_team is this team, reassign
    target_user = await User.find_one(User.user_id == target_user_id)
    if target_user and target_user.current_team == team.id:
        target_user.current_team = None
        await target_user.save()
        await ensure_current_team(target_user)


async def ensure_current_team(user: User) -> Team:
    """Ensure user has a current_team. Create personal team if needed."""
    if user.current_team:
        team = await Team.get(user.current_team)
        if team:
            return team

    # Find first membership
    membership = await TeamMembership.find_one(
        TeamMembership.user_id == user.user_id
    )
    if membership:
        team = await Team.get(membership.team)
        if team:
            user.current_team = team.id
            await user.save()
            return team

    # Create personal team
    team = Team(
        uuid=uuid.uuid4().hex,
        name=f"{user.name or user.user_id}'s Team",
        owner_user_id=user.user_id,
    )
    await team.insert()
    m = TeamMembership(team=team.id, user_id=user.user_id, role="owner")
    await m.insert()
    user.current_team = team.id
    await user.save()
    return team


async def ensure_shared_folder(team: Team) -> SmartFolder:
    """Ensure the team has a shared root folder."""
    folder = await SmartFolder.find_one(
        SmartFolder.team_id == team.uuid,
        SmartFolder.is_shared_team_root == True,  # noqa: E712
    )
    if folder:
        return folder

    folder = SmartFolder(
        parent_id="0",
        title=f"{team.name} Shared",
        uuid=uuid.uuid4().hex,
        team_id=team.uuid,
        is_shared_team_root=True,
    )
    await folder.insert()
    return folder


async def transfer_ownership(
    team_uuid: str, current_owner_id: str, new_owner_id: str
) -> Team:
    """Transfer team ownership to another member."""
    team = await Team.find_one(Team.uuid == team_uuid)
    if not team:
        raise ValueError("Team not found")

    current_m = await _get_membership(team.id, current_owner_id)
    if not current_m or current_m.role != "owner":
        raise ValueError("Only the team owner can transfer ownership")

    new_m = await _get_membership(team.id, new_owner_id)
    if not new_m:
        raise ValueError("New owner must be a member of the team")

    # Demote current owner to admin
    current_m.role = "admin"
    await current_m.save()

    # Promote new owner
    new_m.role = "owner"
    await new_m.save()

    # Update team record
    team.owner_user_id = new_owner_id
    await team.save()

    return team


async def delete_team(team_uuid: str, actor_id: str) -> bool:
    """Delete a team and all associated records. Actor must be owner."""
    team = await Team.find_one(Team.uuid == team_uuid)
    if not team:
        raise ValueError("Team not found")

    actor_m = await _get_membership(team.id, actor_id)
    if not actor_m or actor_m.role != "owner":
        raise ValueError("Only the team owner can delete the team")

    # Delete all memberships for this team
    await TeamMembership.find(TeamMembership.team == team.id).delete()

    # Delete all invites for this team
    await TeamInvite.find(TeamInvite.team == team.id).delete()

    # Clear current_team for any user pointing to this team
    users_with_team = await User.find(User.current_team == team.id).to_list()
    for u in users_with_team:
        u.current_team = None
        await u.save()

    # Delete the team document
    await team.delete()

    return True


# --- helpers ---

async def _get_membership(
    team_id: PydanticObjectId, user_id: str
) -> TeamMembership | None:
    return await TeamMembership.find_one(
        TeamMembership.team == team_id,
        TeamMembership.user_id == user_id,
    )


def _require_min_role(membership: TeamMembership | None, min_role: str) -> None:
    if not membership:
        raise ValueError("Not a member of this team")
    if ROLE_RANK.get(membership.role, 99) > ROLE_RANK.get(min_role, 99):
        raise ValueError(f"Requires at least {min_role} role")
