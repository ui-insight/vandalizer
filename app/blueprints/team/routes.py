import secrets

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
    if team:
        members = TeamMembership.objects(team=team)
        invites = TeamInvite.objects(team=team, accepted=False)
    return render_template(
        "teams/team.html",
        team=team,
        members=members,
        invites=invites,
        current_team=current_team,
        is_admin=is_admin_user(user.user_id),
        current_user_name=user.name,
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


@teams.route("/invite", methods=["POST"])
def team_invite():
    user = require_login()
    team_id = request.form.get("team_id")
    email = request.form.get("email", "").strip().lower()
    role = request.form.get("role", "member")
    team = Team.objects(id=team_id).first()

    if not team:
        return jsonify({"error": "Team not found"}), 404

    membership = TeamMembership.objects(team=team, user_id=user.user_id).first()
    if not membership or membership.role not in ("owner", "admin"):
        return jsonify({"error": "Forbidden"}), 403

    token = secrets.token_urlsafe(24)
    TeamInvite(
        team=team, email=email, role=role, invited_by_user_id=user.user_id, token=token
    ).save()

    # Construct acceptance URL
    accept_url = url_for("team.team_accept_invite", token=token, _external=True)

    # --- Send email ---
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
    TeamMembership(team=inv.team, user_id=user.user_id, role=inv.role).save()
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
    return redirect(url_for("team.team_index"))
