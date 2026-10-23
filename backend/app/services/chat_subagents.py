"""Read-only sub-runs for bulk document analysis (uplift plan Phase 9).

The main chat agent's context is the scarce resource: reading eight full
proposals inline either blows the budget or triggers compaction. Instead,
``analyze_documents`` (chat_tools) fans out one sub-run per document through
this module — each sub-run is a fresh, TOOL-LESS agent that receives a single
document's text plus the instruction, and returns only its (capped) analysis.
The main context sees summaries, never full texts.

Design notes:
- Tool-less by construction. The plan sketched a narrow read-only toolset,
  but the sub-run's entire world is the one document already in its prompt —
  giving it tools adds loop overhead and failure modes for nothing. This also
  makes sub-runs trivially read-only: there is nothing they *can* mutate.
- Same model as the main conversation (plan open question #3: start simple,
  add a SystemConfig knob if token costs demand it).
- Metering and transient retries come for free: create_chat_agent builds on
  get_agent_model, so MeteredModel attributes usage to the caller's active
  scope (the chat turn's ActivityEvent) and RetryingModel absorbs blips.
- Bounded by a module-level semaphore so concurrent analyze_documents calls
  (the tool is parallel-safe) share one global cap instead of multiplying.
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

# Global concurrency cap across ALL in-flight sub-runs in this process.
SUBAGENT_MAX_CONCURRENCY = 4
_subagent_semaphore = asyncio.Semaphore(SUBAGENT_MAX_CONCURRENCY)

# Each per-document analysis is capped before it enters the main context —
# the whole point is that the main agent gets digests, not payloads.
SUBAGENT_RESULT_MAX_CHARS = 6_000

# Reserved for the instruction + framing around the document text.
_PROMPT_OVERHEAD_TOKENS = 2_000

SUBAGENT_SYSTEM_PROMPT = (
    "You are a focused document-analysis assistant. You receive ONE document "
    "and ONE instruction; you know nothing else about the wider conversation.\n"
    "- Follow the instruction exactly and answer from the document text only.\n"
    "- Ground every claim in the document. If the document does not contain "
    "what the instruction asks for, say so plainly — never guess or fill in "
    "from general knowledge.\n"
    "- Preserve exact names, figures, dates, and identifiers.\n"
    "- Be concise: a few hundred words unless the instruction demands "
    "structure (tables, per-field lists).\n"
    "- Output the analysis directly — no preamble, no restating the "
    "instruction."
)


async def analyze_one_document(
    *,
    doc_uuid: str,
    doc_title: str,
    raw_text: str,
    instruction: str,
    model_name: str,
    sys_config_doc: dict,
) -> dict:
    """Run one tool-less sub-analysis; never raises — errors return per-doc.

    The document text is trimmed to the model's effective window (head+tail
    preserved) so a single oversized document degrades gracefully instead of
    failing the whole fan-out.
    """
    from app.services.context_budget import (
        _truncate_text_to_tokens,
        effective_input_window,
        resolve_context_window,
    )
    from app.services.llm_service import _get_model_config_sync, create_chat_agent

    try:
        model_config = _get_model_config_sync(model_name, sys_config_doc)
        window = resolve_context_window(model_name, model_config)
        text_budget = max(1_000, effective_input_window(window) - _PROMPT_OVERHEAD_TOKENS)
        text, dropped = _truncate_text_to_tokens(raw_text, text_budget, model_name)

        prompt = (
            f"Instruction: {instruction}\n\n"
            f"--- BEGIN DOCUMENT: {doc_title} ---\n"
            f"{text}\n"
            f"--- END DOCUMENT ---"
        )

        async with _subagent_semaphore:
            agent = create_chat_agent(
                model_name,
                system_prompt=SUBAGENT_SYSTEM_PROMPT,
                system_config_doc=sys_config_doc,
            )
            result = await agent.run(prompt)

        analysis = result.output if hasattr(result, "output") else str(result.data)
        analysis = (analysis or "").strip()
        capped = len(analysis) > SUBAGENT_RESULT_MAX_CHARS
        return {
            "uuid": doc_uuid,
            "title": doc_title,
            "analysis": analysis[:SUBAGENT_RESULT_MAX_CHARS],
            "analysis_capped": capped,
            "document_truncated": dropped > 0,
        }
    except Exception as e:
        logger.warning(
            "Subagent analysis failed for doc=%s model=%s: %s",
            doc_uuid, model_name, e,
        )
        return {
            "uuid": doc_uuid,
            "title": doc_title,
            "error": f"Analysis failed for this document: {e}",
        }


async def fan_out_analyses(
    *,
    documents: list[dict],
    instruction: str,
    model_name: str,
    sys_config_doc: dict,
) -> list[dict]:
    """Analyze documents concurrently (bounded by the global semaphore).

    ``documents``: [{"uuid", "title", "raw_text"}]. Per-document failures
    come back as error entries in position — one bad document never aborts
    the batch.
    """
    tasks = [
        analyze_one_document(
            doc_uuid=d["uuid"],
            doc_title=d["title"],
            raw_text=d["raw_text"],
            instruction=instruction,
            model_name=model_name,
            sys_config_doc=sys_config_doc,
        )
        for d in documents
    ]
    return list(await asyncio.gather(*tasks))
