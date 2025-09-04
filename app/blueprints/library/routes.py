"""Handles file routing."""

from flask import Blueprint, jsonify, render_template, request

library = Blueprint("library", __name__)


def filter_data(filters):
    """Applies filters to the mock data."""
    scope = filters.get("scope")
    item_type = filters.get("type")
    kinds = filters.get("kinds", [])
    query = filters.get("q", "").lower()

    if scope:
        results = [item for item in results if item.get("scope") == scope]

    if item_type and item_type != "all":
        results = [item for item in results if item.get("type") == item_type]

    # Kind filter only applies when 'tasks' or 'all' is selected
    if item_type != "workflows" and kinds:
        results = [
            item
            for item in results
            if item.get("type") == "workflow"
            or (item.get("type") == "task" and item.get("kind") in kinds)
        ]

    if query:
        results = [
            item
            for item in results
            if query in item.get("title", "").lower()
            or query in item.get("meta", "").lower()
        ]

    return results


@library.route("/")
def library_page():
    """
    Renders the main library page.
    Initial state is determined by URL query parameters.
    """
    # Get initial state from URL or set defaults
    scope = request.args.get("scope", "team")
    item_type = request.args.get("type", "workflows")
    # Kinds are comma-separated in URL
    kinds_str = request.args.get("kinds", "extract,prompt,format")
    kinds = kinds_str.split(",") if kinds_str else []
    query = request.args.get("q", "")

    initial_filters = {"scope": scope, "type": item_type, "kinds": kinds, "q": query}

    # Perform initial data filtering for the first page load
    initial_results = filter_data(initial_filters)

    return render_template(
        "index.html",
        scope=scope,
        item_type=item_type,
        kinds=kinds,
        query=query,
        initial_results=initial_results,
    )


@library.route("/filter", methods=["POST"])
def filter_library_items():
    """
    AJAX endpoint to fetch filtered results.
    Returns rendered HTML as a JSON object.
    """
    filters = request.get_json()

    # Get filtered data
    results = filter_data(filters)

    # Render the partial template with the results
    rendered_html = render_template("library/_results.html", results=results)

    return jsonify({"template": rendered_html})
