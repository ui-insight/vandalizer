"""Send back a reply that states figures about a document it never calculated.

Support ticket (NIH R01 budget): asked whether a budget adds up, chat wrote
yearly direct costs and indirect amounts that were neither in the spreadsheet
nor computed by any tool. It had done the sums in its head, left out a row
and got most of them wrong. The ``calculate`` tool exists and the prompt says
to use it; this is the check that doesn't depend on the model listening.

A reply on a turn with attached or read documents is checked the way the
finished answer is (``kb_answer_grounding.unsupported_figures``): every dollar
amount and percentage must appear in a document, the user's message, or a
tool result. Figures that are in none of them, and that no ``calculate`` step
produced, send the reply back once, asking for the arithmetic to be done with
the tool and the working shown.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.messages import ToolReturnPart

from app.services.kb_answer_grounding import (
    bare_amounts_as_money,
    calculated_only,
    tool_output_as_source,
    unsupported_figures,
)

if TYPE_CHECKING:
    from app.services.chat_deps import AgenticChatDeps

MAX_DOCUMENTS = 20
_SHOWN = 8

CALCULATION_RETRY_INSTRUCTION = (
    "Your reply states figures that appear in neither the document(s) nor any tool "
    "result: {figures}. If you worked them out, redo every one with the calculate tool: "
    "list every row of the table that belongs in each sum (every category, every year), "
    "then show the steps and state only the results it returns, saying they were "
    "calculated from the document. If a figure is the document's own, rounded, write it "
    "as the document states it. If it came from somewhere else, say where, or remove it. "
    "Do not repeat your previous reply."
)


def _tool_outputs(ctx: RunContext["AgenticChatDeps"]) -> list[tuple[str, str]]:
    import json

    out = []
    for message in ctx.messages or []:
        for part in getattr(message, "parts", ()):
            if isinstance(part, ToolReturnPart):
                content = part.content
                out.append((part.tool_name or "", content if isinstance(content, str) else json.dumps(content, default=str)))
    return out


async def _document_texts(uuids: list[str]) -> list[str]:
    from app.models.document import SmartDocument

    docs = await SmartDocument.find({"uuid": {"$in": uuids[:MAX_DOCUMENTS]}}).to_list()
    return [doc.raw_text or "" for doc in docs]


async def require_calculated_figures(ctx: RunContext["AgenticChatDeps"], output: str) -> str:
    """Output validator: send back, once per turn, uncalculated figures about documents."""
    deps = ctx.deps
    if ctx.partial_output or deps is None or getattr(deps, "calculation_retry_used", False):
        return output
    uuids = list(dict.fromkeys([*(getattr(deps, "context_document_uuids", None) or []),
                                *(getattr(deps, "documents_read", None) or [])]))
    if not uuids or not unsupported_figures(output, ""):
        return output
    tools = _tool_outputs(ctx)
    documents = await _document_texts(uuids)
    sources = [*documents, *(bare_amounts_as_money(t) for t in documents), getattr(deps, "user_message", "") or "",
               *(tool_output_as_source(text) for name, text in tools if name != "calculate")]
    missing = unsupported_figures(output, "\n".join(sources))
    calculated = calculated_only(missing, output, [text for name, text in tools if name == "calculate"])
    missing = [figure for figure in missing if figure not in calculated]
    if not missing:
        return output
    deps.calculation_retry_used = True
    shown = ", ".join(missing[:_SHOWN]) + (f" and {len(missing) - _SHOWN} more" if len(missing) > _SHOWN else "")
    raise ModelRetry(CALCULATION_RETRY_INSTRUCTION.format(figures=shown))
