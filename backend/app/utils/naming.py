"""Shared validation for user-facing entity names.

Workflows, folders, extractions, prompts, formatters, knowledge bases,
automations and library folders all let the user type a free-form name. Keep
the rules in one place so naming behaves consistently across the app and a
single pathological title can't blow out list / sidebar layouts.

The matching client-side rules live in
``frontend/src/utils/nameValidation.ts`` — keep the two in sync.
"""

import re
import unicodedata
from typing import Annotated, Optional

from pydantic import AfterValidator

# Keep in sync with MAX_NAME_LENGTH in frontend/src/utils/nameValidation.ts
MAX_NAME_LENGTH = 100

# Runs of any whitespace (incl. newlines / tabs) collapse to a single space so a
# pasted multi-line title renders as one tidy line everywhere it's shown.
_WHITESPACE_RUN = re.compile(r"\s+")


def normalize_entity_name(value: str) -> str:
    """Strip control characters and collapse whitespace. Does not validate.

    Drops Unicode "Other" category code points (control / format / surrogate),
    keeping ordinary whitespace for the collapse step, then squeezes whitespace
    runs to a single space and trims the ends.
    """
    cleaned = "".join(
        ch for ch in value
        if ch.isspace() or unicodedata.category(ch)[0] != "C"
    )
    return _WHITESPACE_RUN.sub(" ", cleaned).strip()


def validate_entity_name(value: str) -> str:
    """Normalize and validate a required name. Raises ``ValueError`` if invalid."""
    if not isinstance(value, str):
        raise ValueError("Name must be text.")
    cleaned = normalize_entity_name(value)
    if not cleaned:
        raise ValueError("Name cannot be empty.")
    if len(cleaned) > MAX_NAME_LENGTH:
        raise ValueError(f"Name must be {MAX_NAME_LENGTH} characters or fewer.")
    return cleaned


def validate_optional_entity_name(value: Optional[str]) -> Optional[str]:
    """Like :func:`validate_entity_name` but passes ``None`` through.

    Used for PATCH / update bodies where the name field is omitted to mean
    "leave unchanged" rather than "clear it".
    """
    if value is None:
        return None
    return validate_entity_name(value)


# Reusable Pydantic field types. Use ``EntityName`` for create requests (name is
# required) and ``OptionalEntityName`` for update requests (name may be omitted).
EntityName = Annotated[str, AfterValidator(validate_entity_name)]
OptionalEntityName = Annotated[Optional[str], AfterValidator(validate_optional_entity_name)]
