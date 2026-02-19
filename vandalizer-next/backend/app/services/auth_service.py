import uuid

from app.models.user import User
from app.models.team import Team, TeamMembership
from app.utils.security import hash_password, verify_password


async def authenticate(user_id: str, password: str) -> User | None:
    user = await User.find_one(User.user_id == user_id)
    if not user:
        user = await User.find_one(User.email == user_id)
    if not user or not user.password_hash:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


async def register(user_id: str, email: str, password: str, name: str | None = None) -> User:
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

    team_uuid = uuid.uuid4().hex
    team = Team(
        uuid=team_uuid,
        name=f"{user_id}'s Team",
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

    return user
