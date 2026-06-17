"""Workflow test-case generator — proposes expected outputs without manual saves.

The workflow optimizer (workflow_optimizer.run_optimization) hard-errors with
"No test inputs available" unless the user has marked past WorkflowResults as
expected_outputs on the Validate tab. This generator removes that gate:

* ``propose_from_history`` scans recent completed runs and proposes each as a
  candidate expected output, with an LLM-drafted label, a confidence score,
  and a short ``why``. The user reviews and accepts a subset.
* ``synthesize_seed_input`` is the fallback when no run history exists: it
  asks an LLM to draft a candidate input document the user can paste in and
  run the workflow against, generating real history on the first run.

Proposals are returned as in-memory dicts; nothing persists until
``accept_proposals`` is called, which turns each accepted proposal into a
real ``expected_output`` entry in ``Workflow.validation_inputs`` (same shape
``save_expected_output`` produces).
"""

from __future__ import annotations

import datetime
import json
import logging
import re
import uuid as uuid_mod

from pydantic_ai import Agent

from app.models.system_config import SystemConfig
from app.models.user import User
from app.models.workflow import Workflow, WorkflowResult
from app.services.config_service import get_user_model_name
from app.services.llm_service import get_agent_model
from app.services.workflow_diagnostics import _looks_like_error

logger = logging.getLogger(__name__)


# How many recent completed runs to consider as candidate test cases. Past 20
# the prompt grows long enough to start losing focus; the user is unlikely to
# accept more than 5-10 anyway.
MAX_CANDIDATE_RESULTS = 20

# Minimum output length (chars) for a result to be considered a viable test
# case. Sub-50-char outputs are almost always error stubs or trivial single-
# token responses that won't exercise the validation plan.
MIN_OUTPUT_LENGTH = 50

# Cap on output text shown in the proposal preview. Keeps the UI fast and the
# accept-flow snapshot bounded; full output_snapshot is grabbed from the
# WorkflowResult at accept time, not from the preview.
PREVIEW_CHARS = 600


PROPOSAL_SYSTEM_PROMPT = (
    "You are reviewing past executions of an automated workflow to nominate "
    "which ones make good 'expected output' examples for validation.\n\n"
    "A good expected output is:\n"
    "- COMPLETE: the workflow finished and produced a real result, not an error\n"
    "- REPRESENTATIVE: the output exercises the workflow's intended purpose\n"
    "- DISTINCT: different from other examples in the set (don't double-count near-duplicates)\n\n"
    "For each candidate, you must return:\n"
    "- ``session_id``: copy from input\n"
    "- ``label``: 3-7 word descriptive title (e.g. 'NSF grant abstract — 2024 Smith proposal')\n"
    "- ``confidence``: float in [0, 1] — how good a test case this is\n"
    "- ``why``: one short sentence explaining the confidence score\n\n"
    "Be honest with confidence. Mark low confidence (<0.3) when output looks "
    "thin, broken, or near-duplicate of another candidate. Return ONLY a JSON "
    "object: {\"proposals\": [...]}."
)


SYNTHESIS_SYSTEM_PROMPT = (
    "You are drafting a realistic test input for an automated document-processing "
    "workflow that has no past executions yet. Given the workflow's name, "
    "description, and step intents, produce a single plausible input document "
    "the user could feed the workflow to exercise it end-to-end.\n\n"
    "The input should be:\n"
    "- REALISTIC: read like a real document of that type (memo, abstract, contract excerpt, etc.)\n"
    "- COMPLETE ENOUGH: contain the fields/sections the workflow expects to find\n"
    "- CONCISE: 200-600 words, not a full novel\n\n"
    "Return ONLY a JSON object: "
    '{"label": "short title", "text": "the full document text"}.'
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def propose_from_history(
    workflow_id: str,
    user: User,
    *,
    limit: int = 5,
) -> dict:
    """Scan recent runs and return candidate test cases with LLM-scored labels.

    The user reviews the result and calls ``accept_proposals`` with the
    session_ids they want to keep. Nothing persists in this function.

    Returns:
        {
          "proposals": [
            {
              "session_id": str,
              "suggested_label": str,
              "output_preview": str,        # truncated
              "confidence": float,           # 0-1
              "why": str,                    # short rationale
              "already_saved": bool,         # already an expected_output
              "created_at": str ISO,
            },
            ...
          ],
          "skipped": {
            "empty_or_error": int,            # filtered before LLM
            "too_short": int,
            "duplicates": int,                # already-saved entries
          },
          "synthesized": false,
        }
    """
    from app.services.workflow_service import _serialize_output, get_authorized_workflow

    wf = await get_authorized_workflow(workflow_id, user)
    if not wf:
        raise ValueError("Workflow not found")

    already_saved_session_ids = {
        inp.get("session_id") for inp in (wf.validation_inputs or [])
        if inp.get("type") == "expected_output" and inp.get("session_id")
    }

    # Pull recent completed runs. Dict-style query — matches the convention
    # used by workflow_optimizer so this service stays testable without the
    # Beanie ``init_db`` wiring (field-access form raises AttributeError when
    # models aren't registered).
    recent = await WorkflowResult.find(
        {"workflow": wf.id, "status": "completed"},
    ).sort("-_id").limit(MAX_CANDIDATE_RESULTS).to_list()

    skipped = {"empty_or_error": 0, "too_short": 0, "duplicates": 0}
    candidates: list[dict] = []

    for wr in recent:
        if wr.session_id in already_saved_session_ids:
            skipped["duplicates"] += 1
            continue

        output_text = _serialize_output(wr.final_output)
        if output_text is None:
            # Binary output — skip; can't be saved as expected output anyway.
            skipped["empty_or_error"] += 1
            continue

        stripped = output_text.strip()
        if not stripped or _looks_like_error(stripped):
            skipped["empty_or_error"] += 1
            continue
        if len(stripped) < MIN_OUTPUT_LENGTH:
            skipped["too_short"] += 1
            continue

        candidates.append({
            "session_id": wr.session_id,
            "output_preview": stripped[:PREVIEW_CHARS],
            "output_length": len(stripped),
            "created_at": wr.start_time.isoformat() if wr.start_time else None,
        })

    if not candidates:
        return {
            "proposals": [],
            "skipped": skipped,
            "synthesized": False,
            "note": "No usable past runs. Run the workflow at least once, or use synthesize.",
        }

    # Cap how many we score with the LLM — the user only wants the top few.
    scoring_pool = candidates[: max(limit * 2, limit)]

    proposals = await _score_candidates_with_llm(
        wf=wf,
        candidates=scoring_pool,
        user_id=user.user_id,
        limit=limit,
    )

    return {
        "proposals": proposals,
        "skipped": skipped,
        "synthesized": False,
    }


async def synthesize_seed_input(
    workflow_id: str,
    user: User,
) -> dict:
    """Draft a single candidate input document for a workflow with no history.

    Returns:
        {
          "label": str,
          "text": str,
          "synthesized": true,
        }
    """
    from app.services.workflow_service import get_authorized_workflow, get_workflow

    wf = await get_authorized_workflow(workflow_id, user)
    if not wf:
        raise ValueError("Workflow not found")

    wf_data = await get_workflow(workflow_id)
    if not wf_data:
        raise ValueError("Workflow not found")

    prompt = _build_synthesis_prompt(wf_data)
    raw = await _run_llm(prompt, SYNTHESIS_SYSTEM_PROMPT, user.user_id)
    parsed = _extract_json(raw) or {}

    label = str(parsed.get("label") or "Synthesized test input").strip()
    text = str(parsed.get("text") or "").strip()
    if not text:
        raise ValueError("Could not synthesize a test input — the LLM returned no content")

    return {
        "label": label,
        "text": text,
        "synthesized": True,
    }


async def accept_proposals(
    workflow_id: str,
    user: User,
    session_ids: list[str],
    *,
    label_overrides: dict[str, str] | None = None,
) -> dict:
    """Persist the accepted proposals as expected_output entries.

    ``label_overrides`` maps session_id → user-edited label. When absent, the
    LLM-suggested label is used (regenerated here from the WorkflowResult).

    Returns:
        {"accepted": list[dict], "skipped": list[{session_id, reason}]}
    """
    from app.services.workflow_service import _serialize_output, get_authorized_workflow

    wf = await get_authorized_workflow(workflow_id, user, manage=True)
    if not wf:
        raise ValueError("Workflow not found")

    label_overrides = label_overrides or {}

    accepted: list[dict] = []
    skipped: list[dict] = []

    # Existing already-saved set so re-accepting a session is a no-op.
    existing_sessions = {
        inp.get("session_id") for inp in (wf.validation_inputs or [])
        if inp.get("type") == "expected_output"
    }

    for session_id in session_ids:
        if session_id in existing_sessions:
            skipped.append({"session_id": session_id, "reason": "already saved"})
            continue

        wr = await WorkflowResult.find_one(
            {"session_id": session_id, "workflow": wf.id, "status": "completed"},
        )
        if not wr:
            skipped.append({"session_id": session_id, "reason": "result not found"})
            continue

        output_text = _serialize_output(wr.final_output)
        if output_text is None:
            skipped.append({"session_id": session_id, "reason": "binary output"})
            continue

        label = label_overrides.get(session_id) or f"Test case from {session_id[:8]}"
        expected_entry = {
            "id": str(uuid_mod.uuid4()),
            "type": "expected_output",
            "session_id": session_id,
            "label": label,
            "output_text": output_text[:50_000],
            "output_snapshot": wr.final_output,
            "steps_output_snapshot": wr.steps_output,
            "source": "test_case_generator",
        }
        wf.validation_inputs.append(expected_entry)
        accepted.append(expected_entry)

    if accepted:
        wf.updated_at = datetime.datetime.now(tz=datetime.timezone.utc)
        await wf.save()

    return {"accepted": accepted, "skipped": skipped}


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------


async def _score_candidates_with_llm(
    *,
    wf: Workflow,
    candidates: list[dict],
    user_id: str,
    limit: int,
) -> list[dict]:
    """Single LLM call that scores all candidates and returns top ``limit``.

    On LLM failure: fall back to deterministic labels + 0.5 confidence so the
    user still sees the candidates and can accept manually.
    """
    user_prompt = _build_proposal_prompt(wf, candidates)
    try:
        raw = await _run_llm(user_prompt, PROPOSAL_SYSTEM_PROMPT, user_id)
        parsed = _extract_json(raw) or {}
        scored = _parse_proposals(parsed, candidates)
    except Exception as e:
        logger.warning("Test case proposal scoring failed: %s — falling back to deterministic labels", e)
        scored = _fallback_proposals(candidates)

    # Sort by confidence desc, then most-recent first as tiebreak.
    scored.sort(key=lambda p: (-p.get("confidence", 0.0), p.get("created_at") or ""), reverse=False)
    scored.sort(key=lambda p: -p.get("confidence", 0.0))
    return scored[:limit]


def _parse_proposals(parsed: dict, candidates: list[dict]) -> list[dict]:
    """Match LLM-scored entries back to candidates by session_id.

    Drops entries the LLM hallucinated session_ids for. Fills in missing
    candidates from the input with a low-confidence fallback so the user can
    still review them.
    """
    by_session = {c["session_id"]: c for c in candidates}
    items = parsed.get("proposals") if isinstance(parsed, dict) else None
    if not isinstance(items, list):
        items = []

    seen: set[str] = set()
    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("session_id", "")).strip()
        cand = by_session.get(sid)
        if not cand:
            continue
        try:
            conf = float(item.get("confidence", 0.5))
        except (TypeError, ValueError):
            conf = 0.5
        conf = max(0.0, min(1.0, conf))
        label = str(item.get("label", "")).strip() or f"Test case from {sid[:8]}"
        why = str(item.get("why", "")).strip()
        seen.add(sid)
        out.append({
            "session_id": sid,
            "suggested_label": label,
            "output_preview": cand["output_preview"],
            "output_length": cand["output_length"],
            "confidence": conf,
            "why": why,
            "already_saved": False,
            "created_at": cand.get("created_at"),
        })

    # Fill in any unscored candidates with a fallback so user sees them too.
    for cand in candidates:
        if cand["session_id"] in seen:
            continue
        out.append(_fallback_proposal(cand))

    return out


def _fallback_proposals(candidates: list[dict]) -> list[dict]:
    return [_fallback_proposal(c) for c in candidates]


def _fallback_proposal(cand: dict) -> dict:
    return {
        "session_id": cand["session_id"],
        "suggested_label": f"Test case from {cand['session_id'][:8]}",
        "output_preview": cand["output_preview"],
        "output_length": cand["output_length"],
        "confidence": 0.5,
        "why": "Generator unavailable — falling back to deterministic label.",
        "already_saved": False,
        "created_at": cand.get("created_at"),
    }


def _build_proposal_prompt(wf: Workflow, candidates: list[dict]) -> str:
    """Build the user prompt for the proposal-scoring LLM call.

    Includes the workflow's name + description so the LLM can judge how well
    each candidate exercises the workflow's intended purpose.
    """
    lines = [
        f"Workflow: {wf.name}",
    ]
    if wf.description:
        lines.append(f"Description: {wf.description}")
    lines.append("")
    lines.append(f"Candidate past executions ({len(candidates)}):")
    lines.append("")
    for c in candidates:
        lines.append(f"### session_id: {c['session_id']}")
        lines.append(f"output_length: {c['output_length']} chars")
        lines.append("output_preview:")
        lines.append(c["output_preview"])
        lines.append("")
    lines.append(
        "Return a JSON object with a 'proposals' list. Score each candidate by "
        "how good a test case it makes for validating this workflow."
    )
    return "\n".join(lines)


def _build_synthesis_prompt(wf_data: dict) -> str:
    name = (wf_data.get("name") or "").strip()
    desc = (wf_data.get("description") or "").strip()
    parts: list[str] = [f"Workflow name: {name}"]
    if desc:
        parts.append(f"Description: {desc}")

    step_intents: list[str] = []
    for s in wf_data.get("steps") or []:
        if not isinstance(s, dict):
            continue
        sname = (s.get("name") or "").strip()
        sdesc = (s.get("description") or "").strip()
        if sname and sdesc:
            step_intents.append(f"- {sname}: {sdesc}")
        elif sname:
            step_intents.append(f"- {sname}")

    if step_intents:
        parts.append("Steps performed by the workflow:")
        parts.append("\n".join(step_intents))

    parts.append("")
    parts.append(
        "Draft one realistic input document this workflow could process. Return "
        "JSON: {\"label\": \"...\", \"text\": \"...\"}."
    )
    return "\n".join(parts)


async def _run_llm(user_prompt: str, system_prompt: str, user_id: str) -> str:
    """Resolve the user's model + run an Agent with the given prompts."""
    model_name = await get_user_model_name(user_id)
    if not model_name:
        raise ValueError("No LLM model configured")

    sys_config = await SystemConfig.get_config()
    sys_config_doc = sys_config.model_dump() if sys_config else None
    model = get_agent_model(model_name, system_config_doc=sys_config_doc)
    agent = Agent(model, system_prompt=system_prompt)
    result = await agent.run(user_prompt)
    return result.output or ""


_FENCE_RE = re.compile(r"^```\w*\n?")


def _extract_json(text: str) -> dict | None:
    """Best-effort JSON object extraction from LLM output.

    Returns None on failure rather than raising — callers fall back to
    deterministic behavior.
    """
    if not text:
        return None
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = _FENCE_RE.sub("", stripped)
        if stripped.endswith("```"):
            stripped = stripped[:-3]
        stripped = stripped.strip()

    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # Locate outermost {...} block as a fallback.
    start = stripped.find("{")
    end = stripped.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            parsed = json.loads(stripped[start:end])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    return None
