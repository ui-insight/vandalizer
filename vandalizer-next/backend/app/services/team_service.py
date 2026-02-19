import secrets
import uuid

from beanie import PydanticObjectId

from app.models.folder import SmartFolder
from app.models.team import Team, TeamInvite, TeamMembership
from app.models.user import User

ROLE_RANK = {"owner": 0, "admin": 1, "member": 2}


async def get_user_teams(user_id: str) -> list[dict]:
    """Get all teams the user belongs to, with their role."""
    memberships = await TeamMembership.find(
        TeamMembership.user_id == user_id
    ).to_list()
    result = []
    for m in memberships:
        team = await Team.get(m.team)
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
    result = []
    for m in memberships:
        user = await User.find_one(User.user_id == m.user_id)
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
        TeamInvite.accepted == False,
    ).to_list()
    return [
        {
            "id": str(inv.id),
            "email": inv.email,
            "role": inv.role,
            "accepted": inv.accepted,
            "token": inv.token,
        }
        for inv in invites
    ]


async def create_team(name: str, user_id: str) -> Team:
    """Create a new team with the user as owner."""
    team = Team(
        uuid=secrets.token_urlsafe(12),
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
    team_uuid: str, email: str, role: str, actor_user_id: str
) -> TeamInvite:
    """Invite a user to a team by email."""
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
        return existing

    invite = TeamInvite(
        team=team.id,
        email=email,
        invited_by_user_id=actor_user_id,
        role=role,
        token=secrets.token_urlsafe(32),
    )
    await invite.insert()
    return invite


async def accept_invite(token: str, user: User) -> Team:
    """Accept a team invitation."""
    invite = await TeamInvite.find_one(TeamInvite.token == token)
    if not invite:
        raise ValueError("Invalid invite token")

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

    invite.accepted = True
    await invite.save()

    user.current_team = team.id
    await user.save()

    return team


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
    """Remove a member from a team."""
    team = await Team.find_one(Team.uuid == team_uuid)
    if not team:
        raise ValueError("Team not found")

    actor_m = await _get_membership(team.id, actor_user_id)
    _require_min_role(actor_m, "admin")

    target_m = await _get_membership(team.id, target_user_id)
    if not target_m:
        raise ValueError("Target user is not a member")

    # Cannot remove an owner
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


async def ensure_shared_folder(team: Team, space_id: str) -> SmartFolder:
    """Ensure the team has a shared root folder for this space."""
    folder = await SmartFolder.find_one(
        SmartFolder.team_id == team.uuid,
        SmartFolder.is_shared_team_root == True,
    )
    if folder:
        if folder.space != space_id:
            folder.space = space_id
            await folder.save()
        return folder

    folder = SmartFolder(
        parent_id="0",
        title=f"{team.name} Shared",
        uuid=uuid.uuid4().hex,
        space=space_id,
        team_id=team.uuid,
        is_shared_team_root=True,
    )
    await folder.insert()
    return folder


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
