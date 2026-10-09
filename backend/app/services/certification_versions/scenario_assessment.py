"""Deterministic grading for versioned recognition scenarios in an unpublished design.

No XP or certification is awarded here. A delivery integration must persist an
explicit learner submission against the pinned bank before using this result.
"""
from typing import Literal

from pydantic import Field, model_validator

from .attempts import encode
from .outcomes import ContractModel


class ScenarioChoice(ContractModel):
    id: str = Field(pattern=r'^[a-z][a-z0-9_]*$')
    text: str = Field(min_length=5)
    feedback: str = Field(min_length=10)


class ScenarioQuestion(ContractModel):
    id: str
    outcome_id: str
    prompt: str = Field(min_length=20)
    choices: tuple[ScenarioChoice, ...] = Field(min_length=2)
    correct_choice_id: str

    @model_validator(mode='after')
    def unique_choices(self):
        ids = [choice.id for choice in self.choices]
        if len(ids) != len(set(ids)) or self.correct_choice_id not in ids:
            raise ValueError('Scenario choices must be unique and contain the keyed answer')
        return self


class ScenarioBank(ContractModel):
    schema_version: Literal[1] = 1
    bank_id: str
    revision: int = Field(ge=1)
    rubric_id: str
    module_id: str
    outcome_ids: tuple[str, ...] = Field(min_length=1)
    questions: tuple[ScenarioQuestion, ...] = Field(min_length=1)

    @model_validator(mode='after')
    def coverage(self):
        ids = [question.id for question in self.questions]
        if len(ids) != len(set(ids)) or len(self.outcome_ids) != len(set(self.outcome_ids)):
            raise ValueError('Scenario and outcome identities must be unique')
        if {question.outcome_id for question in self.questions} != set(self.outcome_ids):
            raise ValueError('Each declared outcome must have assessed scenarios')
        if any(not outcome.startswith(self.module_id + '.') for outcome in self.outcome_ids):
            raise ValueError('Scenario outcomes must belong to the declared module')
        return self

    @property
    def digest(self):
        return encode(self.model_dump(mode='json'))[1]

    def verify_contract(self, contract):
        module = next((module for module in contract.modules if module.module_id == self.module_id), None)
        required = {outcome.id for outcome in module.outcomes if outcome.method == 'scenario_choice'} if module else set()
        if self.rubric_id != contract.rubric_id or set(self.outcome_ids) != required:
            raise ValueError('Scenario bank does not match the declared recognition outcomes and rubric')

    def public_definition(self):
        return {
            'bank_id': self.bank_id, 'revision': self.revision, 'bank_sha256': self.digest,
            'module_id': self.module_id,
            'questions': [{'id': question.id, 'prompt': question.prompt,
                           'choices': [{'id': choice.id, 'text': choice.text} for choice in question.choices]}
                          for question in self.questions],
        }

    def grade(self, answers: dict[str, str], *, expected_sha256: str):
        if expected_sha256 != self.digest:
            raise ValueError('Scenario requirements changed; use the pinned assessment bank')
        if not isinstance(answers, dict) or set(answers) - {question.id for question in self.questions}:
            raise ValueError('Submission contains unknown scenario identities')
        checks = []
        for question in self.questions:
            answer = answers.get(question.id)
            choice = next((choice for choice in question.choices if choice.id == answer), None)
            if answer is not None and choice is None:
                raise ValueError('Submission contains an unknown choice')
            passed = answer == question.correct_choice_id
            checks.append({'id': question.id, 'outcome_id': question.outcome_id, 'role': 'required',
                           'name': question.prompt, 'passed': passed,
                           'detail': choice.feedback if choice else 'Choose an answer for this required case.'})
        outcomes = [{'outcome_id': outcome, 'passed': all(check['passed'] for check in checks if check['outcome_id'] == outcome)}
                    for outcome in self.outcome_ids]
        return {'bank_id': self.bank_id, 'bank_sha256': self.digest, 'rubric_id': self.rubric_id,
                'passed': all(check['passed'] for check in checks), 'checks': checks, 'outcomes': outcomes,
                'assessment_kind': 'scenario_recognition', 'credit_awarded': False}
