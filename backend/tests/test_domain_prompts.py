"""Pure function tests for app.services.domain_prompts.

Verifies template lookup, admin override, field hints, and fuzzy matching.
"""

from app.services.domain_prompts import get_domain_template, get_field_hint


class TestGetDomainTemplate:
    def test_nsf_returns_template(self):
        """Known domain 'nsf' returns a valid template dict."""
        template = get_domain_template("nsf")
        assert template is not None
        assert "name" in template
        assert "NSF" in template["name"]
        assert "system_supplement" in template
        assert "field_hints" in template

    def test_unknown_returns_none(self):
        """Unknown domain returns None."""
        result = get_domain_template("unknown")
        assert result is None

    def test_admin_override_takes_precedence(self):
        """Admin-supplied override for a domain replaces the built-in template."""
        override_template = {
            "name": "Custom NSF",
            "system_supplement": "Custom prompt",
            "field_hints": {"custom_field": "custom hint"},
        }
        result = get_domain_template("nsf", admin_overrides={"nsf": override_template})
        assert result is not None
        assert result["name"] == "Custom NSF"
        assert result["system_supplement"] == "Custom prompt"

    def test_admin_override_for_different_domain_does_not_affect(self):
        """Override for a different domain does not affect the requested one."""
        result = get_domain_template("nsf", admin_overrides={"nih": {"name": "Custom NIH"}})
        assert result is not None
        assert "NSF" in result["name"]

    def test_nih_template_exists(self):
        """NIH domain returns a valid template."""
        template = get_domain_template("nih")
        assert template is not None
        assert "NIH" in template["name"]

    def test_dod_template_exists(self):
        """DOD domain returns a valid template."""
        template = get_domain_template("dod")
        assert template is not None
        assert "DOD" in template["name"]

    def test_doe_template_exists(self):
        """DOE domain returns a valid template."""
        template = get_domain_template("doe")
        assert template is not None
        assert "DOE" in template["name"]


class TestGetFieldHint:
    def test_exact_match(self):
        """Exact field name returns the corresponding hint."""
        hint = get_field_hint("nsf", "award_number")
        assert hint is not None
        assert "7-digit" in hint

    def test_fuzzy_match_case_insensitive(self):
        """Case-insensitive match with spaces converted to underscores works."""
        hint = get_field_hint("nsf", "Award Number")
        assert hint is not None
        assert "7-digit" in hint

    def test_fuzzy_match_uppercase(self):
        """All-uppercase field name still matches."""
        hint = get_field_hint("nsf", "AWARD_NUMBER")
        assert hint is not None
        assert "7-digit" in hint

    def test_nonexistent_field_returns_none(self):
        """Nonexistent field returns None."""
        result = get_field_hint("nsf", "nonexistent")
        assert result is None

    def test_unknown_domain_returns_none(self):
        """Field hint for unknown domain returns None."""
        result = get_field_hint("unknown_domain", "award_number")
        assert result is None

    def test_nih_field_hint(self):
        """NIH domain field hint works."""
        hint = get_field_hint("nih", "grant_number")
        assert hint is not None
        assert "NIH" in hint

    def test_field_hint_with_admin_override(self):
        """Admin override replaces field hints too."""
        override = {
            "nsf": {
                "name": "Override NSF",
                "field_hints": {"custom_key": "custom value"},
            },
        }
        hint = get_field_hint("nsf", "custom_key", admin_overrides=override)
        assert hint == "custom value"

        # Original field should not exist in override
        hint2 = get_field_hint("nsf", "award_number", admin_overrides=override)
        assert hint2 is None
