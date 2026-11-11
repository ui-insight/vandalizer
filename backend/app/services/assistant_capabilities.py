"""What chat can use, grouped for people, with a switch per group.

Chat registers about seventy tool functions. A person deciding what the
Assistant may reach thinks in the work those functions do ("search the web",
"run workflows"), so every tool belongs to exactly one capability here.

Two switches apply to a capability, both stored as "off" lists so a new
capability starts on for everyone:

* an admin's limit for the deployment (``SystemConfig.assistant_capabilities_off``)
* a person's own choice (``User.assistant_capabilities_off``)

A capability that is off is withheld from the model on every request
(``gate`` is each tool's pydantic-ai ``prepare`` hook), and chat is told which
are off so it says so and points at the Assistant page instead of working
around the gap. Tools in ``ALWAYS_ON`` have no switch: approvals, the plan,
help, Skills and reading the person's own files are what chat is.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import ToolDefinition


@dataclass(frozen=True)
class Capability:
    id: str
    label: str
    description: str
    tools: tuple[str, ...]


# Shown on the Assistant page as "Always on", so the page is the whole picture.
ALWAYS_ON: tuple[Capability, ...] = (
    Capability(
        "files", "Read your files",
        "Finds, opens and reads the files and folders you can already see, and does arithmetic on their figures.",
        ("search_documents", "list_documents", "list_folders", "get_document_text", "analyze_documents",
         "calculate", "search_library", "get_quality_info"),
    ),
    Capability(
        "skills", "Skills",
        "Finds your Library Skills, applies the one you choose, and uses your core Skills when a task matches.",
        ("list_skills", "get_skill", "select_skill", "use_core_skill"),
    ),
    Capability(
        "guidance", "Plans, help and certification",
        "Keeps a checklist for multi-step requests, answers how-to questions about the app, and runs the certification course.",
        ("update_plan", "get_app_help", "get_certification_progress", "get_certification_module",
         "get_certification_lesson", "save_certification_position", "provision_certification_lab",
         "check_certification_module", "complete_certification_module", "submit_certification_assessment"),
    ),
)

CAPABILITIES: tuple[Capability, ...] = (
    Capability(
        "web_search", "Search the web",
        "Looks up current information on the public web, such as a sponsor's latest notice.",
        ("web_search",),
    ),
    Capability(
        "web_pages", "Read a web page",
        "Opens a public link you paste and reads the page.",
        ("fetch_url",),
    ),
    Capability(
        "knowledge_bases", "Knowledge bases",
        "Searches your knowledge bases for answers with citations, and can create one or add sources to it.",
        ("search_knowledge_base", "list_knowledge_bases", "create_knowledge_base", "add_documents_to_kb", "add_url_to_kb"),
    ),
    Capability(
        "extractions", "Extractions and compliance checks",
        "Pulls named fields out of a document with a saved extraction, and checks a document against requirements.",
        ("list_extraction_sets", "run_extraction", "check_compliance", "create_extraction_from_document"),
    ),
    Capability(
        "workflows", "Workflows",
        "Runs your saved workflows, reports on a run, handles its approval steps, and can build or edit a workflow.",
        ("list_workflows", "run_workflow", "get_workflow_status", "approve_workflow_step", "reject_workflow_step",
         "create_workflow", "get_workflow_definition", "update_workflow"),
    ),
    Capability(
        "automations", "Automations",
        "Sets up an automation that starts a workflow on its own, for example when a file lands in a folder.",
        ("create_automation",),
    ),
    Capability(
        "validation", "Testing and tuning",
        "Builds test cases, runs validation, and suggests or applies setting changes that improve accuracy.",
        ("list_test_cases", "propose_test_case", "run_validation", "list_optimization_recommendations",
         "get_optimization_run", "start_optimization", "apply_optimization", "regenerate_validation_plan"),
    ),
    Capability(
        "pages", "Pages",
        "Creates and revises shareable Pages, finds saved ones, and fills Page templates from your files.",
        ("find_page_templates", "get_page_template", "create_html_artifact", "find_pages", "get_html_artifact",
         "compare_page_versions", "revise_html_artifact"),
    ),
    Capability(
        "save_files", "Save files to your folders",
        "Saves what chat wrote as a Word, Excel, Markdown or text file in a folder you choose.",
        ("save_to_folder",),
    ),
    Capability(
        "projects", "Projects",
        "Creates projects, moves files into them, pins tools to them, and builds an award snapshot.",
        ("create_project", "list_projects", "move_documents_to_project", "list_project_documents",
         "run_pin_on_project", "pin_to_project", "unpin_from_project", "set_project_status", "get_award_snapshot"),
    ),
    Capability(
        "ra_inbox", "RA inbox",
        "Reads a project's deadlines and required material, and proposes new items it finds in your documents.",
        ("list_project_inbox", "propose_obligations"),
    ),
)

_BY_ID = {c.id: c for c in CAPABILITIES}
_CAPABILITY_OF = {tool: c.id for c in CAPABILITIES for tool in c.tools}


def clean_ids(ids: object) -> list[str]:
    """Known switchable ids, in page order, once each."""
    wanted = {i for i in ids if isinstance(i, str)} if isinstance(ids, (list, tuple, set, frozenset)) else set()
    return [c.id for c in CAPABILITIES if c.id in wanted]


def off_for(user: Any, system_config_doc: dict | None) -> frozenset[str]:
    """Capabilities this person's chat goes without: the admin's limit plus their own."""
    admin = clean_ids((system_config_doc or {}).get("assistant_capabilities_off"))
    own = clean_ids(getattr(user, "assistant_capabilities_off", None))
    return frozenset(admin) | frozenset(own)


async def gate(context: RunContext[Any], tool_def: ToolDefinition) -> ToolDefinition | None:
    """Withhold a tool whose capability is off for this request."""
    off = getattr(context.deps, "capabilities_off", None)
    if off and _CAPABILITY_OF.get(tool_def.name) in off:
        return None
    return tool_def


def instructions(off: frozenset[str]) -> str:
    """Tell chat what is off, so it says so instead of improvising."""
    names = [c.label for c in CAPABILITIES if c.id in off]
    if not names:
        return ""
    return (
        "\n\nThese capabilities are turned off for this person, so their tools are not available to you: "
        + "; ".join(names)
        + ". If a request needs one, say that it is turned off and that it can be turned on at "
        "[Assistant settings](/assistant), unless an administrator has turned it off for everyone. "
        "Do not attempt the task another way, claim you did it, or answer from memory in its place. "
        "Other requests are unaffected."
    )


def describe(user: Any, system_config_doc: dict | None) -> dict:
    """The Assistant page: every capability, who switched it off, and what is always on."""
    config = system_config_doc or {}
    admin_off = set(clean_ids(config.get("assistant_capabilities_off")))
    own_off = set(clean_ids(getattr(user, "assistant_capabilities_off", None)))
    from app.services import web_search_service

    not_set_up = set() if web_search_service.is_configured(config) else {"web_search"}
    rows = []
    for c in CAPABILITIES:
        allowed = c.id not in admin_off
        rows.append({
            "id": c.id, "label": c.label, "description": c.description,
            # What the person chose, kept while an admin limit hides it.
            "enabled": c.id not in own_off,
            "allowed": allowed,
            "available": c.id not in not_set_up,
            "active": allowed and c.id not in own_off and c.id not in not_set_up,
        })
    return {
        "capabilities": rows,
        "always_on": [{"id": c.id, "label": c.label, "description": c.description} for c in ALWAYS_ON],
    }
