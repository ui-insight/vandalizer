"""Run authored synthetic review cases; never infer release readiness from a pass."""
from typing import Literal

from pydantic import Field, model_validator

from .automatic_review import ReviewEvidence, evaluate_draft_structured_review
from .attempts import encode
from .outcomes import ContractModel


class ReviewCalibrationCase(ContractModel):
    id: str
    reason: str = Field(min_length=20)
    evidence: tuple[ReviewEvidence, ...] = Field(min_length=1, max_length=128)
    expected: dict[str, Literal['supported', 'contradicted', 'unclear']]


class ReviewCalibrationSuite(ContractModel):
    schema_version: Literal[1] = 1
    suite_id: str
    module_id: str
    rubric_id: str
    synthetic: Literal[True] = True
    cases: tuple[ReviewCalibrationCase, ...] = Field(min_length=3)

    @model_validator(mode='after')
    def unique_cases(self):
        if len({case.id for case in self.cases}) != len(self.cases):
            raise ValueError('Calibration case identities must be unique')
        return self

    def verify_contract(self, contract):
        module = next((module for module in contract.modules if module.module_id == self.module_id), None)
        required = {outcome.id for outcome in module.outcomes if outcome.method == 'structured_review'} if module else set()
        if not required or contract.rubric_id != self.rubric_id:
            raise ValueError('Calibration requires the matching structured-review module and rubric')
        if any(set(case.expected) != required for case in self.cases):
            raise ValueError('Every calibration case must specify each reviewed outcome')
        for outcome_id in required:
            if not {'supported', 'contradicted'} <= {case.expected[outcome_id] for case in self.cases}:
                raise ValueError('Each reviewed outcome needs positive and negative calibration')
        if not any('unclear' in case.expected.values() for case in self.cases):
            raise ValueError('Automatic-only grading needs an unclear-evidence calibration case')


async def run_review_calibration(contract, suite, *, model_name, system_config, call_model=None):
    suite.verify_contract(contract)
    rows = []
    for case in suite.cases:
        result = await evaluate_draft_structured_review(contract, suite.module_id, case.evidence,
            model_name=model_name, system_config=system_config, call_model=call_model)
        actual = {item['outcome_id']: item['verdict'] for item in result['outcomes']}
        unavailable = result['status'] == 'grading_unavailable'
        false_support = [outcome for outcome, expected in case.expected.items()
                         if expected != 'supported' and actual.get(outcome) == 'supported']
        rows.append({'case_id': case.id, 'expected': case.expected, 'actual': actual,
                     'matches': not unavailable and actual == case.expected,
                     'false_supported_outcomes': false_support, 'grading_unavailable': unavailable,
                     'review_result': result})
    return {'suite_id': suite.suite_id, 'suite_sha256': encode(suite.model_dump(mode='json'))[1],
            'synthetic': True, 'cases': rows, 'all_cases_matched': all(row['matches'] for row in rows),
            'false_support_count': sum(len(row['false_supported_outcomes']) for row in rows),
            'unavailable_cases': sum(row['grading_unavailable'] for row in rows),
            'release_ready': False, 'credit_awarded': False}
