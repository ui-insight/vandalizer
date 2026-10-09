"""Authored competency contract, separate from legacy participation credit.

This validates the mapping used to design a course. It does not assess a learner
or make a draft enrollable. Delivery/rubric implementation is tracked explicitly.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ContractModel(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)


class CalibrationCase(ContractModel):
    id: str
    situation: str = Field(min_length=10)
    expected: Literal['pass', 'fail', 'review']
    reason: str = Field(min_length=10)


class Outcome(ContractModel):
    id: str = Field(pattern=r'^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$')
    statement: str = Field(min_length=20)
    lesson_ids: tuple[str, ...] = Field(min_length=1)
    practice: str = Field(min_length=20)
    assessment: str = Field(min_length=20)
    evidence: tuple[str, ...] = Field(min_length=1)
    passing_conditions: tuple[str, ...] = Field(min_length=1)
    critical_failures: tuple[str, ...] = Field(min_length=1)
    method: Literal['deterministic', 'scenario_choice', 'structured_review']
    calibration: tuple[CalibrationCase, ...] = Field(min_length=2)
    teaching_status: Literal['revision_required', 'authored']
    assessment_status: Literal['not_implemented', 'implemented', 'verified']

    @model_validator(mode='after')
    def validate_cases(self):
        ids = [case.id for case in self.calibration]
        if len(ids) != len(set(ids)) or not {'pass', 'fail'} <= {case.expected for case in self.calibration}:
            raise ValueError('Every outcome needs unique passing and failing calibration cases')
        if len(self.lesson_ids) != len(set(self.lesson_ids)):
            raise ValueError('Repeated lesson reference')
        return self


class ModuleOutcomes(ContractModel):
    module_id: str
    outcomes: tuple[Outcome, ...] = Field(min_length=1)


class OutcomeContract(ContractModel):
    schema_version: Literal[1] = 1
    contract_id: str
    rubric_id: str
    state: Literal['design_draft', 'release_candidate']
    credential_promise: str
    agent_assistance: str
    exclusions: tuple[str, ...] = Field(min_length=1)
    credit_policy: Literal['all_required_outcomes']
    legacy_equivalence: Literal['no_automatic_transfer_without_assessed_evidence']
    evidence_policy: tuple[str, ...] = Field(min_length=1)
    modules: tuple[ModuleOutcomes, ...] = Field(min_length=1)

    @model_validator(mode='after')
    def validate_identities(self):
        modules = [module.module_id for module in self.modules]
        outcomes = [outcome for module in self.modules for outcome in module.outcomes]
        ids = [outcome.id for outcome in outcomes]
        if len(modules) != len(set(modules)) or len(ids) != len(set(ids)):
            raise ValueError('Module and outcome identities must be unique')
        for module in self.modules:
            if any(outcome.id.split('.')[0] != module.module_id for outcome in module.outcomes):
                raise ValueError('An outcome must belong to its named module')
        if self.state == 'release_candidate' and any(
            outcome.teaching_status != 'authored' or outcome.assessment_status != 'verified' for outcome in outcomes
        ):
            raise ValueError('A release candidate requires authored teaching and verified assessments')
        return self

    def verify_teaching_references(self, lessons: dict):
        """A design may reference lessons that need revision; never invent IDs."""
        if {module.module_id for module in self.modules} != set(lessons):
            raise ValueError('Outcome coverage must match the course modules exactly')
        for module in self.modules:
            available = {lesson['id'] for lesson in lessons[module.module_id]['lessons']}
            if any(not set(outcome.lesson_ids) <= available for outcome in module.outcomes):
                raise ValueError(f'Unknown teaching reference in {module.module_id}')

    def required_outcomes(self):
        return tuple(outcome.id for module in self.modules for outcome in module.outcomes)


def package_outcomes(package):
    """Validate optional competency assets without assigning them to old credit."""
    if 'outcomes.json' not in package.manifest.artifacts:
        return None
    contract = OutcomeContract.model_validate_json(package.read('outcomes.json'))
    contract.verify_teaching_references(package.json('lessons.json'))
    if contract.rubric_id != package.manifest.rubric_id:
        raise ValueError('Outcome and grading rubric identities differ')
    if package.entry.state != 'draft' and contract.state != 'release_candidate':
        raise ValueError('Published outcomes require a verified release candidate')
    return contract
