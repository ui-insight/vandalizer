"""Unit tests for Role Spine Layer 2 — role_inference normalizer.

Integration tests that touch MongoDB (approval-flow propagation, backfill
script behavior) live in tier-2 integration tests.
"""

from app.services.role_inference import normalize_role_tags, validate_role_tags


# ---------------------------------------------------------------------------
# normalize_role_tags — exact canonical matches
# ---------------------------------------------------------------------------

def test_canonical_role_value_round_trips():
    assert normalize_role_tags("compliance", None) == ["compliance"]
    assert normalize_role_tags("research_admin", None) == ["research_admin"]
    assert normalize_role_tags("sponsored_programs", None) == ["sponsored_programs"]
    assert normalize_role_tags("pi", None) == ["pi"]
    assert normalize_role_tags("it", None) == ["it"]
    assert normalize_role_tags("other", None) == ["other"]


# ---------------------------------------------------------------------------
# Free-text submitter_role matching
# ---------------------------------------------------------------------------

def test_research_administrator_phrase_maps():
    assert normalize_role_tags("Research Administrator", None) == ["research_admin"]
    assert normalize_role_tags("research administration", None) == ["research_admin"]


def test_principal_investigator_phrase_maps():
    assert normalize_role_tags("Principal Investigator", None) == ["pi"]
    assert normalize_role_tags("PI", None) == ["pi"]


def test_sponsored_programs_aliases_map():
    assert normalize_role_tags("Office of Sponsored Programs", None) == ["sponsored_programs"]
    assert normalize_role_tags("OSP", None) == ["sponsored_programs"]
    assert normalize_role_tags("Pre-Award Specialist", None) == ["sponsored_programs"]


def test_compliance_aliases_map():
    assert normalize_role_tags("IRB coordinator", None) == ["compliance"]
    assert normalize_role_tags("Conflict of Interest officer", None) == ["compliance"]
    assert normalize_role_tags("Research Compliance", None) == ["compliance"]


def test_it_alias_maps():
    assert normalize_role_tags("IT", None) == ["it"]
    assert normalize_role_tags("Information Technology lead", None) == ["it"]


# ---------------------------------------------------------------------------
# intended_use_tags
# ---------------------------------------------------------------------------

def test_intended_use_tags_contribute():
    tags = ["For compliance team", "IRB protocols"]
    assert normalize_role_tags(None, tags) == ["compliance"]


def test_both_submitter_role_and_tags_combine_deduped():
    result = normalize_role_tags(
        "Sponsored Programs Officer",
        ["For pre-award", "Also useful for compliance reviews"],
    )
    assert set(result) == {"sponsored_programs", "compliance"}
    # Order is insertion-order; submitter_role first.
    assert result[0] == "sponsored_programs"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_empty_input_returns_empty():
    assert normalize_role_tags(None, None) == []
    assert normalize_role_tags("", []) == []
    assert normalize_role_tags("   ", [""]) == []


def test_unknown_string_drops_silently():
    assert normalize_role_tags("Wizard of the Forest", ["literally anything"]) == []


def test_partial_match_does_not_overreach():
    # "it" is a short token — must not match e.g. "audit" or "submit"
    assert normalize_role_tags("audit team", None) == []
    assert normalize_role_tags("submitter", None) == []
    # But the actual canonical equals match must still work
    assert normalize_role_tags("IT", None) == ["it"]


def test_pi_short_token_safe():
    # "pi" must not match e.g. "supervisor" or "API"
    assert normalize_role_tags("Supervisor", None) == []
    assert normalize_role_tags("api architect", None) == []
    assert normalize_role_tags("PI", None) == ["pi"]


def test_case_insensitive():
    assert normalize_role_tags("COMPLIANCE", None) == ["compliance"]
    assert normalize_role_tags("Pi", None) == ["pi"]


def test_dedup_repeated_signals():
    result = normalize_role_tags(
        "compliance officer",
        ["compliance", "IRB", "Conflict of Interest"],
    )
    assert result == ["compliance"]


# ---------------------------------------------------------------------------
# validate_role_tags
# ---------------------------------------------------------------------------

def test_validate_role_tags_keeps_canonical():
    assert validate_role_tags(["compliance", "pi"]) == ["compliance", "pi"]


def test_validate_role_tags_drops_invalid():
    assert validate_role_tags(["compliance", "wizard", "pi"]) == ["compliance", "pi"]


def test_validate_role_tags_handles_empty():
    assert validate_role_tags([]) == []
    assert validate_role_tags(None) == []
