"""LLM-powered suggestions to improve a user's prompt.

Used by the Prompt task editor to let users one-click rewrite their prompt
with a short rationale explaining each change.
"""

import logging

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from app.models.system_config import SystemConfig

logger = logging.getLogger(__name__)


class PromptImprovement(BaseModel):
    improved_prompt: str = Field(description="The rewritten prompt, ready to use as a drop-in replacement.")
    rationale: list[str] = Field(description="3-5 short bullets, each describing one specific change and why it helps.")


_SYSTEM_PROMPT = """You are an expert at improving LLM prompts for document-processing workflows.

You are given:
- An original prompt the user wrote for a "Prompt" task in a workflow.
- The task's input source (where the prompt's input data comes from).
- (Optional) the upstream step's name.
- (Optional) a sample of the typical input.

Rewrite the prompt to be clearer, more specific, and more likely to produce reliable, well-formatted output. Preserve the user's original intent. Do not invent domain knowledge, output requirements, or constraints the user did not ask for.

Common improvements:
- Replace vague verbs ("look at", "process", "handle") with concrete instructions ("extract", "summarize into 3 bullets", "compare X and Y").
- Specify an output format if the user implied one (bullet list, table, JSON, plain prose).
- Acknowledge whether the input is multiple documents, a single document, or upstream step output — and refer to it correctly (don't say "this document" when the input is upstream text from a Formatter step).
- Remove filler, ambiguous pronouns, and conversational scaffolding ("Hey, I was wondering if you could...").

If the original prompt is already well-written, return it essentially unchanged with one rationale bullet saying so.

Do NOT add boilerplate like "You are a helpful assistant" — the system prompt is handled separately. The user's prompt should describe the *task*, not the persona.
"""


def _format_input_source(input_source: str | None) -> str | None:
    if not input_source:
        return None
    return {
        "step_input": "the text output of the previous workflow step",
        "select_document": "a specific document selected by the user",
        "workflow_documents": "the document(s) the workflow is being run on (may be multiple)",
        "kb_grounding": "passages retrieved from the task's knowledge bases as reference material",
    }.get(input_source, input_source)


class GroundingQuerySuggestion(BaseModel):
    queries: list[str] = Field(
        description=(
            "Two to four retrieval queries, each a short noun phrase of 4-12 "
            "words naming ONE topic the task needs policy or guidance on."
        )
    )
    rationale: list[str] = Field(
        description=(
            "One short bullet per query: which passages it should find and "
            "why this task needs them."
        )
    )


_GROUNDING_SYSTEM_PROMPT = """You write retrieval queries for a vector search over knowledge bases of policy and guidance text — federal regulations (e.g. 2 CFR 200), agency grant policy (NSF PAPPG, NIH Grants Policy Statement), and institutional research-administration procedures.

You are given the instructions of one task in a document-processing workflow, and the titles and descriptions of the knowledge bases it will search. The task reads a document (a funding announcement, an award, a budget); the knowledge bases hold the rules that document is interpreted against.

Write the queries that would pull the passages this task needs to do its job well:
- One topic per query. A query that lists several topics embeds as a blur and retrieves none of them well.
- Short noun phrases in the vocabulary the knowledge base itself uses ("cost sharing or matching requirements", "indirect cost rate de minimis waiver"), 4-12 words, no question wording, no "please", no pronouns.
- Target what the listed knowledge bases actually cover. Skip topics none of them would contain.
- Never include values from a specific document (an amount, a date, a program number) — the queries run on every document this workflow processes.
- Two to four queries. Fewer is better than padding.
"""


async def suggest_grounding_queries(
    prompt: str,
    task_name: str | None = None,
    knowledge_bases: list[dict] | None = None,
    max_queries: int = 3,
    user_id: str | None = None,
) -> dict:
    """Draft retrieval queries for a task's knowledge-base grounding.

    Returns ``{"queries": [...], "rationale": [...]}``. Design-time only —
    the author edits the result before saving, so run-time retrieval stays
    deterministic.
    """
    from app.services.config_service import get_default_model_name
    from app.services.llm_service import get_agent_model

    sys_cfg = await SystemConfig.get_config()
    sys_config_doc = sys_cfg.model_dump() if sys_cfg else {}
    default_model = await get_default_model_name() or "gpt-4o-mini"

    max_queries = max(1, min(4, int(max_queries or 3)))
    parts = [f"Task type: {task_name or 'Prompt'}", f"Task instructions:\n```\n{prompt[:6000]}\n```"]
    kb_lines = []
    for kb in knowledge_bases or []:
        if not isinstance(kb, dict):
            continue
        title = (kb.get("title") or "").strip()
        if not title:
            continue
        description = (kb.get("description") or "").strip()
        kb_lines.append(f"- {title}" + (f": {description[:300]}" if description else ""))
    if kb_lines:
        parts.append("Knowledge bases to search:\n" + "\n".join(kb_lines))
    parts.append(f"Write at most {max_queries} queries.")

    model = get_agent_model(default_model, system_config_doc=sys_config_doc)
    agent = Agent(model, system_prompt=_GROUNDING_SYSTEM_PROMPT, output_type=GroundingQuerySuggestion)

    from app.services.metering import metered_async
    async with metered_async("kb_query_suggest", user_id=user_id):
        result = await agent.run("\n\n".join(parts))
    queries = [q.strip() for q in result.output.queries if isinstance(q, str) and q.strip()]
    return {
        "queries": queries[:max_queries],
        "rationale": result.output.rationale[: len(queries[:max_queries])] or result.output.rationale,
    }


async def improve_prompt(
    prompt: str,
    input_source: str | None = None,
    prev_step_name: str | None = None,
    sample_input: str | None = None,
    user_id: str | None = None,
) -> dict:
    """Return a rewritten prompt and a list of rationale bullets.

    ``user_id`` attributes the spend to the requesting user so trial budgets
    count (and can stop) it like every other user-triggered call.
    """
    from app.services.config_service import get_default_model_name
    from app.services.llm_service import get_agent_model

    sys_cfg = await SystemConfig.get_config()
    sys_config_doc = sys_cfg.model_dump() if sys_cfg else {}

    default_model = await get_default_model_name() or "gpt-4o-mini"

    parts = [f"Original prompt:\n```\n{prompt}\n```"]
    readable_source = _format_input_source(input_source)
    if readable_source:
        parts.append(f"\nInput source: {readable_source}")
    if prev_step_name and input_source == "step_input":
        parts.append(f"Previous step name: {prev_step_name}")
    if sample_input:
        excerpt = sample_input[:1500]
        parts.append(f"\nSample of typical input:\n```\n{excerpt}\n```")

    model = get_agent_model(default_model, system_config_doc=sys_config_doc)
    agent = Agent(model, system_prompt=_SYSTEM_PROMPT, output_type=PromptImprovement)

    from app.services.metering import metered_async
    async with metered_async("prompt_improve", user_id=user_id):
        result = await agent.run("\n".join(parts))
    return {
        "improved_prompt": result.output.improved_prompt,
        "rationale": result.output.rationale,
    }
