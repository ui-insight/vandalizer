"""Handles file routing."""

from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from app.models import (  # adjust import path if needed
    Library,
    LibraryItem,
    LibraryScope,
    SearchSet,
    SearchSetItem,
    Team,
    User,
    Workflow,
)

library = Blueprint("library", __name__)

from app.utils import load_user


# -----------------------------
# Helpers to resolve scope
# -----------------------------
def _current_user_id() -> str:
    # Replace with your auth/session lookup
    # e.g. return session["user_id"]
    # For now, assume a dev user:
    return "dev-user-1"


def _current_user() -> User | None:
    return User.objects(user_id=_current_user_id()).first()


def _current_team_for_user(user: User | None) -> Team | None:
    if not user:
        return None
    return user.ensure_current_team()


def _get_or_none_library(
    scope: LibraryScope, *, user: User | None, team: Team | None
) -> Library | None:
    if scope == LibraryScope.PERSONAL:
        if not user:
            return None
        return Library.objects(
            scope=LibraryScope.PERSONAL, owner_user_id=user.user_id
        ).first()
    if scope == LibraryScope.TEAM:
        if not team:
            return None
        return Library.objects(scope=LibraryScope.TEAM, team=team).first()
    if scope == LibraryScope.VERIFIED:
        return Library.objects(scope=LibraryScope.VERIFIED).first()
    return None


def _resolve_scope(scope_str: str) -> LibraryScope:
    """
    Maps UI 'scope' querystrings to your enum.
    UI accepts: 'team' | 'mine' | 'verified'
    """
    scope_str = (scope_str or "").lower()
    if scope_str in ("mine", "personal"):
        return LibraryScope.PERSONAL
    if scope_str == "verified":
        return LibraryScope.VERIFIED
    # default to team
    return LibraryScope.TEAM


# -----------------------------
# Data building for template
# -----------------------------
def _build_results_for_template(filters: dict) -> dict:
    """
    Returns the dict expected by _results.html:
    - workflows
    - extraction_sets
    - prompts
    - formatters
    - scope
    - filters
    """
    scope_in = filters.get("scope") or "team"
    item_type = filters.get("type") or "workflows"
    kinds = filters.get("kinds") or []
    query = (filters.get("q") or "").strip().lower()

    # Resolve library by scope
    user = load_user()
    team = _current_team_for_user(user)
    lib_scope = _resolve_scope(scope_in)
    lib = _get_or_none_library(lib_scope, user=user, team=team)

    # If there is no library yet, present empty lists gracefully
    lib_items: list[LibraryItem] = list(lib.items) if lib else []

    # --- Separate polymorphic objects
    workflow_objs: list[Workflow] = []
    searchset_objs: list[SearchSet] = []
    searchset_items_objs: list[SearchSetItem] = []

    for li in lib_items:
        # li.kind is "workflow" or "searchset"
        if li.kind == "workflow" and li.obj and isinstance(li.obj, Workflow):
            workflow_objs.append(li.obj)
        elif li.kind == "searchset" and li.obj and isinstance(li.obj, SearchSet):
            searchset_objs.append(li.obj)
        elif li.kind == "prompt" and li.obj and isinstance(li.obj, SearchSetItem):
            searchset_items_objs.append(li.obj)
        elif li.kind == "formatter" and li.obj and isinstance(li.obj, SearchSetItem):
            searchset_items_objs.append(li.obj)

    # --- Apply 'type' and 'kinds'
    # type: 'workflows' | 'tasks' | 'all'
    # kinds only affect tasks; in our data model 'extract' maps to SearchSet.set_type == 'extraction'
    # (If you later add Prompt/Formatter collections, wire them similarly.)
    workflows = []
    extraction_sets = []
    prompts = []  # placeholders; not defined in provided model
    formatters = []  # placeholders; not defined in provided model

    print(item_type)

    # Filter workflows
    if item_type in ("workflows", "all"):
        workflows = workflow_objs

    # Filter task sets (SearchSet) by kind
    if item_type in ("tasks", "all"):
        want_extract = (not kinds) or ("extract" in kinds)
        # If you later support 'prompt' & 'format' catalogs, branch here.
        if want_extract:
            extraction_sets = [
                s for s in searchset_objs if (s.set_type or "").lower() == "extraction"
            ]
        prompts = [
            s for s in searchset_items_objs if (s.searchtype or "").lower() == "prompt"
        ]
        formatters = [
            s
            for s in searchset_items_objs
            if (s.searchtype or "").lower() == "formatter"
        ]

    # --- Text search
    if query:
        if workflows:
            workflows = [
                w
                for w in workflows
                if query in (w.name or "").lower()
                or query in (w.description or "").lower()
            ]
        if extraction_sets:
            extraction_sets = [
                s for s in extraction_sets if query in (s.title or "").lower()
            ]
        if prompts:
            prompts = [s for s in prompts if query in (s.title or "").lower()]
        if formatters:
            formatters = [s for s in formatters if query in (s.title or "").lower()]

    # --- Sort (optional niceties)
    workflows.sort(
        key=lambda w: (w.verified is False, (w.updated_at or w.created_at)),
        reverse=True,
    )
    extraction_sets.sort(
        key=lambda s: (s.verified is False, (s.created_at)), reverse=True
    )

    # Assemble context for template
    context = {
        "workflows": workflows,
        "extraction_sets": extraction_sets,
        "prompts": prompts,
        "formatters": formatters,
        "filters": {
            "type": item_type,
            "kinds": kinds,
            "q": query,
        },
        # expose simple scope used in badges in your _results.html
        "scope": "team"
        if lib_scope == LibraryScope.TEAM
        else ("mine" if lib_scope == LibraryScope.PERSONAL else "verified"),
    }
    return context


# -----------------------------
# Routes
# -----------------------------
@library.route("/")
def library_page():
    """
    Renders the main library page.
    Initial state is determined by URL query parameters.
    """
    # Get initial state from URL or set defaults
    scope = request.args.get("scope", "team")  # 'team' | 'mine' | 'verified'
    item_type = request.args.get("type", "workflows")  # 'workflows' | 'tasks' | 'all'
    kinds_str = request.args.get("kinds", "extract,prompt,format")
    kinds = [k for k in kinds_str.split(",") if k] if kinds_str else []
    query = request.args.get("q", "")

    initial_filters = {"scope": scope, "type": item_type, "kinds": kinds, "q": query}
    ctx = _build_results_for_template(initial_filters)

    # Render the partial once for first load so the panel is filled immediately
    initial_results_html = render_template("library/_results.html", **ctx)

    return render_template(
        "index.html",  # your main page template
        scope=scope,
        item_type=item_type,
        kinds=kinds,
        query=query,
        initial_results_html=initial_results_html,
    )


@library.route("/filter", methods=["POST"])
def filter_library_items():
    """
    AJAX endpoint to fetch filtered results.
    Returns rendered HTML as a JSON object.
    """
    filters = request.get_json() or {}
    ctx = _build_results_for_template(filters)
    rendered_html = render_template("library/_results.html", **ctx)
    return jsonify({"template": rendered_html})
