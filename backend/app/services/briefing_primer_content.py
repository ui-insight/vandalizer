"""Curated primer content for Morning Briefings when real activity is scarce.

Used when a user (typically early in their trial) has no recent activity, no team
events, and no role-matched KB news. The primer keeps the daily cadence alive
without firing an empty briefing.

Each role has two pools:
  - "seed_tasks": concrete real-feeling tasks the user could try in chat
  - "capability_tips": short "did you know" capability spotlights

Items are rotated via User.briefing_primer_shown_ids so the same user doesn't see
the same primer two days running.
"""

from typing import Iterable


# A primer item is a dict with keys: id (stable slug), headline, body, deep_link.
PrimerItem = dict


_RESEARCH_ADMIN_SEED_TASKS: list[PrimerItem] = [
    {
        "id": "ra-seed-budget-extract",
        "headline": "Try extracting budget categories from a real proposal",
        "body": "Drop a recent NIH or NSF proposal into chat and ask: 'pull all budget line items by category.' I'll show you the result with a quality score.",
        "deep_link": "/chat?suggest=extract-budget",
    },
    {
        "id": "ra-seed-checklist",
        "headline": "Run a proposal completeness check",
        "body": "Upload any proposal draft and ask me to check it against your sponsor's required elements. I'll flag anything missing.",
        "deep_link": "/chat?suggest=proposal-checklist",
    },
    {
        "id": "ra-seed-award-summary",
        "headline": "Summarize an award letter in 10 seconds",
        "body": "Paste or upload an award notice and ask 'what changed from the proposal?' I'll pull the key award terms with citations.",
        "deep_link": "/chat?suggest=award-summary",
    },
]

_RESEARCH_ADMIN_TIPS: list[PrimerItem] = [
    {
        "id": "ra-tip-quality-score",
        "headline": "Every answer carries a quality score",
        "body": "Look for the colored badge on each result. Below 0.7 means I'm flagging the answer as low-confidence — worth a second look. This is the thing generic AI tools can't give you.",
        "deep_link": "/docs/quality-signals",
    },
    {
        "id": "ra-tip-saved-search",
        "headline": "Saved searches catch new docs that match a pattern",
        "body": "Tell me 'watch for any new proposals that mention human subjects research without an IRB plan' and I'll alert you when one lands.",
        "deep_link": "/chat?suggest=saved-search",
    },
    {
        "id": "ra-tip-workflow-vs-chat",
        "headline": "When to promote a chat task to a workflow",
        "body": "If you ask me the same kind of question across multiple documents, ask 'make this a workflow.' I'll bundle the steps so you can run it on a folder of proposals at once.",
        "deep_link": "/chat?suggest=create-workflow",
    },
]


_PI_SEED_TASKS: list[PrimerItem] = [
    {
        "id": "pi-seed-budget-justification",
        "headline": "Draft a budget justification from your scope",
        "body": "Upload your draft Specific Aims and budget table. Ask: 'write a budget justification matching the aims.' I'll produce a sponsor-ready paragraph.",
        "deep_link": "/chat?suggest=budget-justification",
    },
    {
        "id": "pi-seed-bio-sketch",
        "headline": "Generate an NIH biosketch from a CV",
        "body": "Upload your CV and ask for an NIH biosketch in the current format. I'll pull contributions to science from your publications.",
        "deep_link": "/chat?suggest=biosketch",
    },
    {
        "id": "pi-seed-reviewer-response",
        "headline": "Turn reviewer comments into a response plan",
        "body": "Paste a summary statement and ask 'group critiques by theme and propose responses.' I'll cite the relevant paragraphs and suggest revision priorities.",
        "deep_link": "/chat?suggest=reviewer-response",
    },
]

_PI_TIPS: list[PrimerItem] = [
    {
        "id": "pi-tip-citations",
        "headline": "Every fact I quote points back to a page",
        "body": "Click any source citation in my answers and I'll jump you to the exact paragraph in the source document. No invented references.",
        "deep_link": "/docs/quality-signals",
    },
    {
        "id": "pi-tip-knowledge-base",
        "headline": "Build a KB of your past funded proposals",
        "body": "Upload your last 3-5 funded proposals into a knowledge base, then ask questions like 'what budget categories tend to score well for K awards?'",
        "deep_link": "/chat?suggest=kb-from-proposals",
    },
]


_COMPLIANCE_SEED_TASKS: list[PrimerItem] = [
    {
        "id": "comp-seed-irb-check",
        "headline": "Run an IRB protocol completeness check",
        "body": "Upload an IRB protocol and ask: 'check this against our required elements for human subjects research.' I'll list what's missing or vague.",
        "deep_link": "/chat?suggest=irb-check",
    },
    {
        "id": "comp-seed-coi-scan",
        "headline": "Scan a disclosure for COI red flags",
        "body": "Drop a financial disclosure into chat and ask 'flag anything that looks like a significant financial interest in sponsor entities.' I'll surface the items with citations.",
        "deep_link": "/chat?suggest=coi-scan",
    },
    {
        "id": "comp-seed-subaward-risk",
        "headline": "Assess subaward risk in one pass",
        "body": "Upload a subaward agreement and your risk criteria. Ask 'score this subaward on financial, compliance, and performance risk.' I'll generate a structured risk profile.",
        "deep_link": "/chat?suggest=subaward-risk",
    },
]

_COMPLIANCE_TIPS: list[PrimerItem] = [
    {
        "id": "comp-tip-audit-trail",
        "headline": "Every chat session is auditable",
        "body": "Chat conversations, the documents I touched, and the tool calls I made are recorded. Your audit team can replay any answer I gave.",
        "deep_link": "/docs/quality-signals",
    },
    {
        "id": "comp-tip-validators",
        "headline": "Validators check answers against your policies",
        "body": "Build a validator that says 'every IRB checklist must list a data-sharing plan' and I'll flag any chat answer or workflow result that misses it.",
        "deep_link": "/chat?suggest=create-validator",
    },
]


# Generic pool, used when role_segment is missing or unrecognized.
_GENERIC_SEED_TASKS: list[PrimerItem] = [
    {
        "id": "gen-seed-upload-ask",
        "headline": "Try a real document — any document",
        "body": "Drop any document you have on hand into chat and ask a question about it. Most people are surprised what they get back.",
        "deep_link": "/chat",
    },
    {
        "id": "gen-seed-extract-anything",
        "headline": "Pull structured data out of a messy doc",
        "body": "Upload a document and tell me what fields you want extracted. I'll give you a table with quality scores per field.",
        "deep_link": "/chat?suggest=extract-fields",
    },
]

_GENERIC_TIPS: list[PrimerItem] = [
    {
        "id": "gen-tip-validated-difference",
        "headline": "What makes Vandalizer different from ChatGPT",
        "body": "Every answer comes with a quality score, source citations to the exact paragraph, and a re-runnable workflow you can hand to a teammate. That's not a feature on top — it's the whole product.",
        "deep_link": "/docs/quality-signals",
    },
    {
        "id": "gen-tip-certification",
        "headline": "There's a guided path to mastery",
        "body": "The Certification track walks through 11 modules — from AI literacy to multi-step workflow design. Module 1 is 10 minutes.",
        "deep_link": "/certification",
    },
]


_ROLE_POOLS: dict[str, dict[str, list[PrimerItem]]] = {
    "research_admin": {"seed_tasks": _RESEARCH_ADMIN_SEED_TASKS, "tips": _RESEARCH_ADMIN_TIPS},
    "sponsored_programs": {"seed_tasks": _RESEARCH_ADMIN_SEED_TASKS, "tips": _RESEARCH_ADMIN_TIPS},
    "pi": {"seed_tasks": _PI_SEED_TASKS, "tips": _PI_TIPS},
    "compliance": {"seed_tasks": _COMPLIANCE_SEED_TASKS, "tips": _COMPLIANCE_TIPS},
}


def _pool_for(role_segment: str | None) -> dict[str, list[PrimerItem]]:
    if role_segment and role_segment in _ROLE_POOLS:
        return _ROLE_POOLS[role_segment]
    return {"seed_tasks": _GENERIC_SEED_TASKS, "tips": _GENERIC_TIPS}


def select_seed_tasks(role_segment: str | None, count: int) -> list[PrimerItem]:
    """Return up to `count` seed-task pills for the given role.

    Unlike `select_primer_items` (which mixes seeds + tips for a briefing's
    daily-rotation slot), this returns ONLY seed_tasks — the concrete
    "try this in chat" pills used in the empty-chat WelcomeExperience.
    No dedup is applied; the empty-chat surface is shown only on the first
    session anyway.
    """
    if count <= 0:
        return []
    pool = _pool_for(role_segment)
    return pool["seed_tasks"][:count]


def select_primer_items(
    role_segment: str | None,
    already_shown_ids: Iterable[str],
    count: int,
) -> list[PrimerItem]:
    """Return up to `count` primer items the user hasn't seen yet.

    Alternates seed_tasks and tips to mix concrete CTAs with capability spotlights.
    Falls back to repeating once everything in the pool has been seen.
    """
    if count <= 0:
        return []
    pool = _pool_for(role_segment)
    shown = set(already_shown_ids)

    seeds_unseen = [item for item in pool["seed_tasks"] if item["id"] not in shown]
    tips_unseen = [item for item in pool["tips"] if item["id"] not in shown]

    selected: list[PrimerItem] = []
    # Interleave: first a seed task (concrete try-this), then a tip, repeat.
    while len(selected) < count and (seeds_unseen or tips_unseen):
        if seeds_unseen:
            selected.append(seeds_unseen.pop(0))
            if len(selected) >= count:
                break
        if tips_unseen:
            selected.append(tips_unseen.pop(0))

    if len(selected) < count:
        # Everything's been shown; fall back to the front of each pool.
        leftover_pool = pool["seed_tasks"] + pool["tips"]
        for item in leftover_pool:
            if len(selected) >= count:
                break
            if item not in selected:
                selected.append(item)

    return selected[:count]
