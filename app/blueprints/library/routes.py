"""Handles file routing."""

from flask import Blueprint, jsonify, render_template, request

library = Blueprint("library", __name__)


MOCK_DATA = [
    {
        "id": 1,
        "type": "workflow",
        "scope": "verified",
        "title": "Verified Financial Report Workflow",
        "meta": "Official workflow for quarterly reports.",
    },
    {
        "id": 2,
        "type": "task",
        "kind": "extract",
        "scope": "verified",
        "title": "Extract Invoices",
        "meta": "A verified task to pull invoice data.",
    },
    {
        "id": 3,
        "type": "task",
        "kind": "prompt",
        "scope": "team",
        "title": "Summarize Meeting Notes",
        "meta": "Team prompt for meeting summaries.",
    },
    {
        "id": 4,
        "type": "workflow",
        "scope": "team",
        "title": "Team Onboarding Workflow",
        "meta": "Standard procedure for new hires.",
    },
    {
        "id": 5,
        "type": "task",
        "kind": "format",
        "scope": "team",
        "title": "Format as Memo",
        "meta": "Formats text into the official team memo style.",
    },
    {
        "id": 6,
        "type": "workflow",
        "scope": "mine",
        "title": "My Daily Review",
        "meta": "A personal workflow I created.",
    },
    {
        "id": 7,
        "type": "task",
        "kind": "extract",
        "scope": "mine",
        "title": "Scan for Action Items",
        "meta": "My custom extraction task.",
    },
    {
        "id": 8,
        "type": "task",
        "kind": "prompt",
        "scope": "mine",
        "title": "Draft an Email Reply",
        "meta": "A personal prompt for quick email drafting.",
    },
    {
        "id": 9,
        "type": "task",
        "kind": "format",
        "scope": "verified",
        "title": "APA Citation Formatter",
        "meta": "Formats text to APA 7th edition.",
    },
    {
        "id": 10,
        "type": "workflow",
        "scope": "team",
        "title": "Marketing Campaign Approval",
        "meta": "Multi-step approval workflow for the marketing team.",
    },
]


def filter_data(filters):
    """Applies filters to the mock data."""
    scope = filters.get("scope")
    item_type = filters.get("type")
    kinds = filters.get("kinds", [])
    query = filters.get("q", "").lower()

    results = MOCK_DATA

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
