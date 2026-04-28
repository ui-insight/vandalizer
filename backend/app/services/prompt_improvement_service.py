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
    }.get(input_source, input_source)


async def improve_prompt(
    prompt: str,
    input_source: str | None = None,
    prev_step_name: str | None = None,
    sample_input: str | None = None,
) -> dict:
    """Return a rewritten prompt and a list of rationale bullets."""
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

    result = await agent.run("\n".join(parts))
    return {
        "improved_prompt": result.output.improved_prompt,
        "rationale": result.output.rationale,
    }
