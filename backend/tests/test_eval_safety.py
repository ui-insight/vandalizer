"""Tests that custom_expression rejects sandbox escape attempts.

Verifies the asteval-based sandbox blocks dangerous Python constructs.
"""

import pytest

from app.services.cross_field_validation import CrossFieldValidator


@pytest.fixture
def validator():
    return CrossFieldValidator()


ATTACK_EXPRESSIONS = [
    "__import__('os')",
    "__class__.__bases__",
    "open('/etc/passwd')",
    "exec('print(1)')",
    "globals()",
    "compile('code', '', 'exec')",
    "breakpoint()",
    "[x for x in ().__class__.__bases__[0].__subclasses__()]",
]


class TestSandboxEscapes:
    @pytest.mark.parametrize("expression", ATTACK_EXPRESSIONS)
    def test_attack_rejected(self, validator, expression):
        data = {"a": 1}
        rule = {"type": "custom_expression", "expression": expression}
        results = validator.validate(data, [rule])
        assert len(results) == 1
        assert results[0]["passed"] is False, (
            f"Expression {expression!r} should have been rejected but passed"
        )
