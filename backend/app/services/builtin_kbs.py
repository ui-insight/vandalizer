"""Vandalizer's built-in regulation knowledge bases, used without being attached.

Support ticket: asked "What is the effective date of PAPPG 24-1 Supplement 1?"
with nothing attached, chat answered from memory (Jan 20, 2025) and linked an
NSF page that says Dec. 8, 2025. Asked for the Single Audit threshold, it
searched the web and cited commercial blogs. With the catalog's "NSF PAPPG
Reference" and "OMB Uniform Guidance (2 CFR 200)" attached, both answers were
right and cited. Most people ask without attaching anything.

So a question that names a regulation or sponsor policy consults the matching
built-in knowledge base for that turn, through the same retrieval, citation and
figure checks as an attached one. The match is a deterministic topic list, not
the model's choice: the failure was the model not reaching for them.

Built-in means a verified catalog knowledge base (``resource_config.seed_id``).
Retiring a catalog item clears ``verified``, so retired ones drop out.
"""

from __future__ import annotations

import datetime
import re
from typing import Any

# seed_id → what a question about it says. Patterns are deliberately specific:
# a false match costs a retrieval and a few snippets the KB rules tell the
# model to ignore when off-topic; a miss costs a wrong regulatory answer.
_TOPICS: list[tuple[str, re.Pattern[str]]] = [
    ("kb-2cfr200", re.compile(
        r"\b2\s*c\.?\s*f\.?\s*r\.?\b|\buniform guidance\b|\bomb (?:circular|guidance)\b|\bsingle audits?\b"
        r"|\b(?:§\s*)?200\.\d{3}\b|\bindirect cost rate\b|\bde minimis\b|\bmtdc\b|\bmodified total direct costs?\b"
        r"|\bcost principles\b|\ballowab(?:le|ility)\b|\bsubrecipient\b|\bpass-through entit|\bprocurement standards\b"
        r"|\bprogram income\b|\bcost[- ]shar(?:e|ing)\b|\bequipment threshold\b|\bprior approval\b",
        re.IGNORECASE)),
    ("kb-nsf-pappg", re.compile(
        r"\bpappg\b|\bnsf\b|\bnational science foundation\b|\bproposal (?:&|and) award policies\b", re.IGNORECASE)),
    ("kb-nih-gps", re.compile(
        r"\bnih\b|\bgrants policy statement\b|\bnih ?gps\b|\bnational institutes of health\b|\bsalary cap\b"
        r"|\bnotice of award\b.*\bnih\b|\bmodular budget\b", re.IGNORECASE)),
    ("kb-fcoi", re.compile(
        r"\bfcoi\b|\bfinancial conflicts? of interest\b|\bconflicts? of interest\b|\b42\s*c\.?f\.?r\.?\s*(?:part\s*)?50\b"
        r"|\bsignificant financial interest\b", re.IGNORECASE)),
    ("kb-far", re.compile(
        r"\bfar\s+(?:part|clause|subpart|\d)|\bfederal acquisition regulation\b|\b48\s*c\.?f\.?r\.?\b|\bfar\b(?=[^.?!]{0,40}\b(?:contract|clause|acquisition)\b)",
        re.IGNORECASE)),
    ("kb-common-rule", re.compile(
        r"\bcommon rule\b|\b45\s*c\.?f\.?r\.?\s*(?:part\s*)?46\b|\bhuman (?:research )?subjects?\b|\birb\b"
        r"|\binformed consent\b|\bexempt (?:research|category)\b", re.IGNORECASE)),
    ("kb-export-control", re.compile(
        r"\bexport control|\bexport administration regulations\b|\b\bear\b(?=[^.?!]{0,40}\b(?:export|license|eccn|control)\b)"
        r"|\b15\s*c\.?f\.?r\.?\s*(?:part\s*)?7[3-7]\d\b|\beccn\b|\bdeemed exports?\b|\bitar\b|\bcommerce control list\b",
        re.IGNORECASE)),
    ("kb-rcr", re.compile(
        r"\bresponsible conduct of research\b|\brcr\b|\bresearch misconduct\b|\bdata management (?:and sharing )?plan\b",
        re.IGNORECASE)),
    ("kb-dod-research", re.compile(r"\bdfars\b|\bdod\b|\bdepartment of defense\b|\bdarpa\b|\bonr\b|\bafosr\b", re.IGNORECASE)),
    ("kb-doe-fa", re.compile(r"\bdoe\b|\bdepartment of energy\b|\b2\s*c\.?f\.?r\.?\s*(?:part\s*)?910\b", re.IGNORECASE)),
]

MAX_ROUTED = 2

# A request to do something ("run the NSF budget workflow", "create a KB from
# the PAPPG") is a task for tools, not a policy question: answering it in
# knowledge-base mode would get in the way.
_ACTION = re.compile(
    r"^\s*(?:please\s+)?(?:run|re-?run|create|make|build|save|upload|extract|add|delete|remove|move|open|attach"
    r"|start|draft|write|generate|fill|rename|share|publish|schedule|set up|import|export|send)\b",
    re.IGNORECASE,
)
_QUESTION = re.compile(
    r"\?|^\s*(?:what|when|which|who|whom|where|why|how|is|are|was|were|does|do|did|can|could|may|must|should"
    r"|shall|will|would|has|have|explain|describe|define|list|cite|summari[sz]e|tell me|what's)\b",
    re.IGNORECASE,
)

# A question about the user's own things in Vandalizer ("Can you list my NIH
# workflows?", "How do I attach the PAPPG KB?") names a sponsor but is about
# the app, not the regulation: knowledge-base mode would answer it from
# regulation snippets instead of with tools.
_APP_OBJECT = re.compile(
    r"\b(?:workflows?|extractions?|templates?|folders?|automations?|knowledge bases?|kbs?|vandalizer"
    r"|my (?:documents?|files?|library|projects?|uploads?))\b",
    re.IGNORECASE,
)


def is_policy_question(message: str) -> bool:
    text = message or ""
    return bool(_QUESTION.search(text)) and not _ACTION.search(text) and not _APP_OBJECT.search(text)


def matching_seed_ids(message: str) -> list[str]:
    """Built-in KB seed ids a question is about, most specific first."""
    text = message or ""
    if not is_policy_question(text):
        return []
    return [seed for seed, pattern in _TOPICS if pattern.search(text)][:MAX_ROUTED]


def _searchable(kb: Any) -> bool:
    status = getattr(kb, "status", None)
    return (getattr(kb, "total_chunks", 0) or 0) > 0 and status not in ("empty", "unavailable")


def describe(kb: Any) -> dict:
    updated = getattr(kb, "updated_at", None)
    return {
        "uuid": kb.uuid, "title": kb.title, "description": (kb.description or "").strip(),
        "updated": updated.date().isoformat() if isinstance(updated, datetime.datetime) else None,
    }


async def builtin_kbs() -> list[Any]:
    """Every searchable built-in knowledge base."""
    from app.models.knowledge import KnowledgeBase

    found = await KnowledgeBase.find(
        {"verified": True, "resource_config.seed_id": {"$exists": True, "$ne": None}},
    ).to_list()
    return [kb for kb in found if _searchable(kb)]


async def route(message: str) -> list[Any]:
    """The built-in knowledge bases this question should consult, in topic order."""
    seeds = matching_seed_ids(message)
    if not seeds:
        return []
    # The catalog's own copy (owned by "system") wins over any other verified
    # KB that carries the same seed_id (a legacy KB stamped by title).
    found = sorted(await builtin_kbs(), key=lambda kb: getattr(kb, "user_id", None) == "system")
    by_seed = {(kb.resource_config or {}).get("seed_id"): kb for kb in found}
    return [by_seed[seed] for seed in seeds if seed in by_seed]


def consulted_reminder(kbs: list[dict]) -> str:
    """Told to the model on a turn that consulted built-in KBs it wasn't given."""
    lines = "\n".join(
        f"- {kb['title']}" + (f": {kb['description']}" if kb["description"] else "")
        + (f" (last updated {kb['updated']})" if kb["updated"] else "")
        for kb in kbs
    )
    return (
        "Nothing was attached, but this question is about a regulation or sponsor policy, so "
        "Vandalizer searched its built-in knowledge base(s) for it:\n" + lines + "\n"
        "Answer from these snippets and cite them. Say which knowledge base and edition the "
        "answer reflects (from the description above). If they don't answer the question, say "
        "so; then, if you search the web, prefer the official source (nsf.gov, ecfr.gov, "
        "grants.nih.gov, acquisition.gov, federalregister.gov, hhs.gov) over commercial "
        "sites, and say the answer came from the web, not the knowledge base."
    )


def available_reminder(kbs: list[dict]) -> str:
    """Lists the built-in KBs on turns that didn't consult them automatically."""
    lines = "\n".join(f"- {kb['title']} (kb_uuid {kb['uuid']})" + (f": {kb['description'][:160]}" if kb["description"] else "") for kb in kbs)
    return (
        "Built-in regulation knowledge bases (official texts Vandalizer ships, searchable "
        "without being attached):\n" + lines + "\n"
        "For a question about a regulation or sponsor policy (2 CFR 200, PAPPG, NIH GPS, "
        "FCOI, FAR, Common Rule, export control…), call search_knowledge_base with the "
        "matching kb_uuid BEFORE web_search or answering from memory, cite what it returns "
        "and name the knowledge base and its edition. Use web_search only when they don't "
        "cover it, preferring official sites over commercial ones. If you answer such a "
        "question without any source, say so plainly and suggest attaching the relevant "
        "built-in knowledge base."
    )
