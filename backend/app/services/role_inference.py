"""Map free-text legacy role fields to canonical VALID_ROLE_SEGMENTS values.

`VerificationRequest.submitter_role` and `VerificationRequest.intended_use_tags`
predate the role spine and are unstructured. This module exists to translate
those free-text values into the constrained role_segment vocabulary used by
recommendations.

Approach: case-insensitive substring match against a curated keyword map.
Unknown tokens drop silently. Empty input returns an empty list (= universal
item, visible to all roles).
"""

from app.models.organization import VALID_ROLE_SEGMENTS


# Each canonical role maps to a list of keyword substrings (lowercase).
# The canonical role value itself is always included so already-canonical
# inputs round-trip.
_ROLE_KEYWORDS: dict[str, list[str]] = {
    "research_admin": [
        "research_admin",
        "research admin",
        "research administrator",
        "research administration",
        "office of research",
    ],
    "pi": [
        "pi",
        "principal investigator",
        "faculty",
        "investigator",
    ],
    "sponsored_programs": [
        "sponsored_programs",
        "sponsored programs",
        "sponsored project",
        "osp",
        "pre-award",
        "pre award",
        "post-award",
        "post award",
        "grants management",
    ],
    "compliance": [
        "compliance",
        "irb",
        "iacuc",
        "coi",
        "conflict of interest",
        "human subjects",
        "research compliance",
    ],
    "it": [
        "it",
        "infosec",
        "systems",
        "information technology",
        "security",
    ],
    "other": [
        "other",
    ],
}


def _match_one(token: str) -> str | None:
    """Return the canonical role_segment matching this token, or None."""
    if not token:
        return None
    norm = token.strip().lower()
    if not norm:
        return None
    # Prefer exact-equality matches first so e.g. "it" doesn't fuzzy-match
    # something containing those two letters from another keyword pool.
    for role, keywords in _ROLE_KEYWORDS.items():
        if norm in keywords:
            return role
    for role, keywords in _ROLE_KEYWORDS.items():
        for kw in keywords:
            # "it" and "pi" are too short to safely substring-match; require equality (already covered above).
            if len(kw) < 3:
                continue
            if kw in norm:
                return role
    return None


def normalize_role_tags(
    submitter_role: str | None,
    intended_use_tags: list[str] | None,
) -> list[str]:
    """Normalize legacy free-text role fields to canonical role_segment values.

    Returns a deduped list drawn from VALID_ROLE_SEGMENTS. Empty list = universal.
    """
    found: list[str] = []
    seen: set[str] = set()

    candidates: list[str] = []
    if submitter_role:
        candidates.append(submitter_role)
    if intended_use_tags:
        candidates.extend(t for t in intended_use_tags if t)

    for raw in candidates:
        role = _match_one(raw)
        if role and role in VALID_ROLE_SEGMENTS and role not in seen:
            seen.add(role)
            found.append(role)

    return found


def validate_role_tags(role_tags: list[str] | None) -> list[str]:
    """Validate that every entry is a canonical role_segment. Drops invalid entries."""
    if not role_tags:
        return []
    return [r for r in role_tags if r in VALID_ROLE_SEGMENTS]
