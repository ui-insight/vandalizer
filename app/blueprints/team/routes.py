import secrets

from flask import Blueprint, abort, jsonify, redirect, render_template, request, url_for

from app.models import Team, TeamInvite, TeamMembership
from app.utils import load_user

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


# ---------- TEAM (member-facing) ----------


@teams.route("/", methods=["GET"])
def team_index():
    user = require_login()
    # Find teams the user belongs to (simplest: first one)
    memberships = TeamMembership.objects(user_id=user.user_id)
    team = memberships.first().team if memberships else None
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
    # permission: only owner/admin can invite
    membership = TeamMembership.objects(team=team, user_id=user.user_id).first()
    if not membership or membership.role not in ("owner", "admin"):
        return jsonify({"error": "Forbidden"}), 403
    token = secrets.token_urlsafe(24)
    TeamInvite(
        team=team, email=email, role=role, invited_by_user_id=user.user_id, token=token
    ).save()
    # TODO: send email with accept link: url_for("team.team_accept_invite", token=token, _external=True)
    return redirect(url_for("team.team_index"))


@teams.route("/invite/accept/<token>", methods=["GET"])
def team_accept_invite(token):
    user = require_login()
    inv = TeamInvite.objects(token=token, accepted=False).first()
    if not inv:
        abort(404)
    # Add member
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
    # owner cannot be downgraded except by themselves or another owner (your policy)
    if tm.role == "owner" and actor.role != "owner":
        return jsonify({"error": "Only an owner can change another owner's role"}), 403
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
    if tm.role == "owner":
        return jsonify({"error": "Cannot remove the owner"}), 403
    tm.delete()
    return redirect(url_for("team.team_index"))
