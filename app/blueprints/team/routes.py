import secrets
from datetime import datetime

from flask import Blueprint, abort, jsonify, redirect, render_template, request, url_for
from flask_mail import Message

from app import load_user, mail
from app.models import Team, TeamInvite, TeamMembership, User

teams = Blueprint("team", __name__)


def require_login():
    return load_user()


def is_admin_user(user_id: str) -> bool:
    user = current_user()
    return user.is_admin


def current_user():
    return load_user()


def user_name(user_id: str) -> str:
    return user_id


# ---------- helpers ----------


def _owners_count(team: Team) -> int:
    return TeamMembership.objects(team=team, role="owner").count()


def _is_only_owner(team: Team, user_id: str) -> bool:
    return (
        _owners_count(team) == 1
        and TeamMembership.objects(team=team, user_id=user_id, role="owner").first()
        is not None
    )


# ---------- TEAM (member-facing) ----------


def _get_teams(user: User) -> tuple[Team, list[TeamMembership]]:
    current_team = user.ensure_current_team()
    my_teams = TeamMembership.objects(user_id=user.get_id())
    return (current_team, my_teams)


@teams.route("/", methods=["GET"])
def team_index():
    user = require_login()
    memberships = TeamMembership.objects(user_id=user.user_id)
    team = memberships.first().team if memberships else None
    current_team, my_teams = _get_teams(user)
    members = []
    invites = []
    can_edit_team = False
    team_id: str | None = None
    if team:
        members = TeamMembership.objects(team=team)
        invites = TeamInvite.objects(team=team, accepted=False)
        membership = TeamMembership.objects(team=team, user_id=user.user_id).first()
        if membership and membership.role in ("owner", "admin"):
            can_edit_team = True
        team_id = str(team.id)
    return render_template(
        "teams/team.html",
        team=team,
        members=members,
        invites=invites,
        current_team=current_team,
        is_admin=is_admin_user(user.user_id),
        current_user_name=user.name,
        can_edit_team=can_edit_team,
        team_id=team_id,
    )


@teams.route("/create", methods=["POST"])
def team_create():
    user = require_login()
    name = request.form.get("name", "").strip()
    if not name:
        return jsonify({"error": "Team name is required"}), 400
    t = Team(
        uuid=secrets.token_urlsafe(12), name=name, owner_user_id=user.user_id
    ).save()
    TeamMembership(team=t, user_id=user.user_id, role="owner").save()
    return redirect(url_for("team.team_index"))


@teams.route("/update_name", methods=["POST"])
def update_team_name():
    user = require_login()
    data = request.get_json(silent=True) or {}
    team_id = data.get("team_id")
    new_name = (data.get("name") or "").strip()

    if not team_id or not new_name:
        return jsonify({"error": "Team id and name are required."}), 400

    team = Team.objects(id=team_id).first()
    if not team:
        return jsonify({"error": "Team not found."}), 404

    membership = TeamMembership.objects(team=team, user_id=user.user_id).first()
    if not membership or membership.role not in ("owner", "admin"):
        return jsonify({"error": "You do not have permission to rename this team."}), 403

    team.name = new_name
    team.save()

    return jsonify({"status": "success", "name": team.name})


@teams.route("/invite", methods=["POST"])
def team_invite():
    user = require_login()
    team_id = request.form.get("team_id")
    email = request.form.get("email", "").strip().lower()
    role = request.form.get("role", "member")

    team = Team.objects(id=team_id).first()
    if not team:
        return jsonify({"error": "Team not found"}), 404

    # Only owners/admins may invite
    membership = TeamMembership.objects(team=team, user_id=user.user_id).first()
    if not membership or membership.role not in ("owner", "admin"):
        return jsonify({"error": "Forbidden"}), 403

    # If the email already corresponds to a user who is on the team, short-circuit.
    invitee_user = User.objects(email=email).first()
    if invitee_user:
        existing_member = TeamMembership.objects(
            team=team, user_id=invitee_user.user_id
        ).first()
        if existing_member:
            # Already a member; optionally notify inviter that the user is already on the team.
            return redirect(url_for("team.team_index"))

    # Find or create invite. If one exists and is not accepted, update & resend.
    token = secrets.token_urlsafe(24)
    existing_invite = TeamInvite.objects(team=team, email=email).first()

    if existing_invite:
        if existing_invite.accepted:
            # Already accepted. Treat as no-op (or you could optionally email “you’re already on the team”).
            return redirect(url_for("team.team_index"))

        # Update and RESEND
        existing_invite.role = role
        existing_invite.invited_by_user_id = user.user_id
        existing_invite.token = token
        existing_invite.sent_at = (
            datetime.utcnow()
        )  # add this field to your model if not present
        existing_invite.resend_count = (
            existing_invite.resend_count or 0
        ) + 1  # add this field too
        existing_invite.save()
        invite = existing_invite
    else:
        invite = TeamInvite(
            team=team,
            email=email,
            role=role,
            invited_by_user_id=user.user_id,
            token=token,
            sent_at=datetime.utcnow(),  # optional metadata
            resend_count=0,  # optional metadata
        ).save()

    # Construct acceptance URL
    accept_url = url_for("team.team_accept_invite", token=token, _external=True)

    # Send (or re-send) the email
    try:
        subject = f"You've been invited to join {team.name} on Inkwell"
        body = f"""
Hi there,

{user.name} has invited you to join the team "{team.name}" on Inkwell.

To accept your invitation, click the link below:
{accept_url}

If you did not expect this invitation, you can safely ignore this email.

— The Inkwell Team
"""
        msg = Message(subject=subject, recipients=[email], body=body)
        mail.send(msg)
    except Exception as e:
        print(f"Error sending invite email: {e}")
        return jsonify({"error": "Failed to send invite email"}), 500

    return redirect(url_for("team.team_index"))


@teams.route("/invite/accept/<token>", methods=["GET"])
def team_accept_invite(token):
    user = require_login()
    inv = TeamInvite.objects(token=token, accepted=False).first()
    if not inv:
        abort(404)

    # Check if user is already a member of this team
    existing_membership = TeamMembership.objects(
        team=inv.team, user_id=user.user_id
    ).first()
    if not existing_membership:
        # Create new membership only if they're not already a member
        TeamMembership(team=inv.team, user_id=user.user_id, role=inv.role).save()
        # Update user's current_team if they don't have one
        if not user.current_team:
            user.current_team = inv.team
            user.save()
    # else: User is already a member, just mark invite as accepted

    inv.accepted = True
    inv.save()
    return redirect(url_for("team.team_index"))


@teams.route("/member/role", methods=["POST"])
def team_change_role():
    user = require_login()
    team_id = request.form.get("team_id")
    target_user_id = request.form.get("user_id")
    new_role = request.form.get("role")
    team = Team.objects(id=team_id).first()
    if not team:
        return jsonify({"error": "Team not found"}), 404

    actor = TeamMembership.objects(team=team, user_id=user.user_id).first()
    if not actor or actor.role not in ("owner", "admin"):
        return jsonify({"error": "Forbidden"}), 403

    tm = TeamMembership.objects(team=team, user_id=target_user_id).first()
    if not tm:
        return jsonify({"error": "Member not found"}), 404

    # Only an owner can change another owner's role
    if tm.role == "owner" and actor.role != "owner":
        return jsonify({"error": "Only an owner can change another owner's role"}), 403

    # Do not allow an owner to change their own role (prevents orphaned teams and matches your policy)
    if target_user_id == user.user_id and tm.role == "owner":
        return jsonify({"error": "Owners cannot change their own role."}), 403

    # Never allow demoting the last remaining owner
    if tm.role == "owner" and new_role != "owner" and _is_only_owner(team, tm.user_id):
        return jsonify({"error": "Team must always have at least one owner."}), 403

    tm.role = new_role
    tm.save()
    return redirect(url_for("team.team_index"))


@teams.route("/member/remove", methods=["POST"])
def team_remove_member():
    user = require_login()
    team_id = request.form.get("team_id")
    target_user_id = request.form.get("user_id")
    team = Team.objects(id=team_id).first()
    if not team:
        return jsonify({"error": "Team not found"}), 404

    actor = TeamMembership.objects(team=team, user_id=user.user_id).first()
    if not actor or actor.role not in ("owner", "admin"):
        return jsonify({"error": "Forbidden"}), 403

    tm = TeamMembership.objects(team=team, user_id=target_user_id).first()
    if not tm:
        return jsonify({"error": "Member not found"}), 404

    # Explicitly block an owner from removing themselves
    if target_user_id == user.user_id and tm.role == "owner":
        return jsonify({"error": "Owners cannot remove themselves from the team."}), 403

    # Block removal of any owner (your existing policy)
    if tm.role == "owner":
        return jsonify({"error": "Cannot remove the owner"}), 403

    tm.delete()

    # Reassign the removed user to another team (or create a personal team for them)
    target_user = User.objects(user_id=target_user_id).first()
    if target_user:
        # If their current_team was the one they were just removed from, clear it
        if target_user.current_team and str(target_user.current_team.id) == str(
            team.id
        ):
            target_user.current_team = None
            target_user.save()
        # ensure_current_team will pick/create a default team for them
        target_user.ensure_current_team()

    return redirect(url_for("team.team_index"))
