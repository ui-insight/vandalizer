"""Strict display contracts for certification chat results.

These validate response shape, not learner competence. A bad write response is
uncertain: inspect existing state rather than invoking the operation again.
"""
from functools import wraps
import logging
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError, model_validator

logger = logging.getLogger(__name__)
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Count = Annotated[int, Field(ge=0)]
Stars = Annotated[int, Field(ge=0, le=3)]


class Result(BaseModel):
    model_config = ConfigDict(strict=True, extra='allow')
    enrollment_id: Text | None = None
    course_version: Text | None = None
    course_title: Text | None = None
    manifest_sha256: Text | None = None
    maximum_stars: Annotated[int, Field(ge=1, le=3)] | None = None
    credit_basis: Literal['required_outcomes', 'legacy_rubric'] | None = None

    @model_validator(mode='after')
    def identity(self):
        if self.enrollment_id and not all((self.course_version, self.course_title, self.manifest_sha256)):
            raise ValueError('An enrolled result requires its complete course identity')
        if (self.maximum_stars is None) != (self.credit_basis is None):
            raise ValueError('Reward metadata requires both its scale and credit basis')
        if self.credit_basis == 'required_outcomes' and self.maximum_stars != 1:
            raise ValueError('Required-outcome credit has one completion threshold')
        if (self.maximum_stars is not None and 'stars' in type(self).model_fields
                and self.stars > self.maximum_stars):
            raise ValueError('Stars cannot exceed the pinned course scale')
        return self


class ModuleRow(BaseModel):
    model_config = ConfigDict(strict=True, extra='allow')
    module_id: Text
    title: Text
    xp: Count
    completed: bool
    stars: Stars


class ProgressionSummary(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    policy_id: Text
    state: Literal['design_draft', 'release_candidate']
    required_modules: Annotated[int, Field(gt=0)]
    required_outcomes: Annotated[int, Field(gt=0)]
    base_xp_total: Annotated[int, Field(gt=0)]
    rules: list[Text] = Field(min_length=1)


class ProgressResult(Result):
    total_xp: Count
    level: Text
    certified: bool
    modules_completed: Count
    modules_total: Annotated[int, Field(gt=0)]
    next_module_id: Text | None
    modules: list[ModuleRow] = Field(min_length=1)
    progression_policy: ProgressionSummary | None = None

    @model_validator(mode='after')
    def counts(self):
        ids = [row.module_id for row in self.modules]
        completed = sum(row.completed for row in self.modules)
        if len(set(ids)) != len(ids) or self.modules_total != len(ids) or self.modules_completed != completed:
            raise ValueError('Module counts and identities must match their rows')
        if self.certified and completed != len(ids):
            raise ValueError('Certified progress cannot omit required completed modules')
        if self.next_module_id and not any(row.module_id == self.next_module_id and not row.completed for row in self.modules):
            raise ValueError('The next module must be an incomplete course module')
        if self.maximum_stars is not None and any(row.stars > self.maximum_stars for row in self.modules):
            raise ValueError('Module stars cannot exceed the pinned course scale')
        if self.progression_policy is not None and (
                not self.enrollment_id or self.credit_basis != 'required_outcomes'
                or self.progression_policy.required_modules != self.modules_total
                or self.progression_policy.base_xp_total != sum(row.xp for row in self.modules)):
            raise ValueError('Progression policy must match the pinned course and module rewards')
        return self


class RequiredOutcome(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    outcome_id: Text
    statement: Text
    method: Literal['deterministic', 'scenario_choice', 'structured_review']


class ModuleResult(Result):
    module_id: Text
    title: Text
    xp: Count
    completed: bool
    stars: Stars
    overview: str
    instructions: list[Text]
    agent_guidance: list[Text] = Field(default_factory=list)
    lesson_titles: list[Text]
    expected_fields: list[Text]
    star_criteria: dict[str, Text]
    sample_documents: list[Text]
    provisioned_docs: list[Text]
    assessment_keys: list[Text]
    assessment_questions: list[dict]
    assessment_mode: Literal['legacy_reflection', 'legacy_practical', 'selected_saved_outcomes'] | None = None
    required_outcomes: list[RequiredOutcome] = Field(default_factory=list)
    selected_outcome_completion: bool = False

    @model_validator(mode='after')
    def criteria(self):
        if not set(self.star_criteria) <= {'1', '2', '3'}:
            raise ValueError('Star criteria must name supported star counts')
        ids = [outcome.outcome_id for outcome in self.required_outcomes]
        if self.assessment_mode == 'selected_saved_outcomes':
            if (not ids or len(ids) != len(set(ids)) or self.assessment_keys or self.assessment_questions
                    or any(not identity.startswith(self.module_id + '.') for identity in ids)):
                raise ValueError('Selected-outcome instructions must match this module without legacy reflection keys')
        elif self.required_outcomes or self.selected_outcome_completion:
            raise ValueError('Outcome requirements cannot be attached to a legacy assessment route')
        return self


class KnowledgeOption(BaseModel):
    model_config = ConfigDict(strict=True, extra='allow')
    text: Text
    correct: bool
    explanation: Text


class KnowledgeCheck(BaseModel):
    model_config = ConfigDict(strict=True, extra='allow')
    question: Text
    options: list[KnowledgeOption] = Field(min_length=2)

    @model_validator(mode='after')
    def one_answer(self):
        if sum(option.correct for option in self.options) != 1:
            raise ValueError('Practice requires exactly one correct answer')
        return self


class LessonResult(Result):
    module_id: Text
    module_title: Text
    title: Text
    content: Text
    objective: str
    lesson_number: Annotated[int, Field(gt=0)]
    lesson_count: Annotated[int, Field(gt=0)]
    is_last: bool
    knowledge_check: KnowledgeCheck | None = None
    diagram: str | None = None

    @model_validator(mode='after')
    def position(self):
        if self.lesson_number > self.lesson_count or self.is_last != (self.lesson_number == self.lesson_count):
            raise ValueError('Lesson position must agree with the course sequence')
        return self


class CheckRow(BaseModel):
    model_config = ConfigDict(strict=True, extra='allow')
    role: Literal['required', 'advisory'] | None = None
    name: Text
    passed: bool
    detail: str


class CheckResult(Result):
    module_id: Text
    title: Text
    passed: bool
    stars: Stars
    checks: list[CheckRow] = Field(min_length=1)

    @model_validator(mode='after')
    def required_summary(self):
        if any(check.role is not None for check in self.checks):
            required = [check for check in self.checks if check.role == 'required']
            if (any(check.role is None for check in self.checks) or not required
                    or self.passed != all(check.passed for check in required)):
                raise ValueError('The summary must match every required check')
        return self


class CompletionResult(Result):
    module_id: Text
    title: Text
    stars: Stars
    xp_earned: Count
    total_xp: Count
    level: Text
    level_up: bool
    certified: bool
    credit_origin: Literal['transferred'] | None = None
    xp_carried: Count | None = None
    source_enrollment_id: Text | None = None

    @model_validator(mode='after')
    def reward(self):
        if self.xp_earned > self.total_xp:
            raise ValueError('Awarded XP cannot exceed the resulting total')
        if self.credit_origin == 'transferred':
            if self.xp_earned != 0 or self.xp_carried is None or self.xp_carried > self.total_xp or not self.source_enrollment_id:
                raise ValueError('Transferred credit must separate carried XP from new rewards')
        elif self.xp_carried is not None or self.source_enrollment_id is not None:
            raise ValueError('Transfer metadata requires its explicit credit origin')
        return self


class ProvisionResult(Result):
    module_id: Text
    provisioned_docs: list[Text]
    document_names: list[Text]
    folder: Text
    message: Text


class ReflectionResult(Result):
    module_id: Text
    stored: bool
    message: Text

    @model_validator(mode='after')
    def saved(self):
        if self.stored is not True:
            raise ValueError('A saved-answer response must confirm storage')
        return self


def certification_result(schema: type[Result]):
    """Keep the original payload and signature; never coerce or repeat work."""
    def decorate(function):
        @wraps(function)
        async def wrapped(*args, **kwargs):
            try:
                result = await function(*args, **kwargs)
                if isinstance(result, dict) and isinstance(result.get('error'), str) and result['error'].strip():
                    return result
                schema.model_validate(result)
                return result
            except (ValidationError, KeyError, TypeError, AttributeError):
                # Log the operation name only: validation errors may contain
                # learner answers or source data and must not enter this log.
                logger.warning('Certification response contract failed for %s', function.__name__)
                return {
                    'error': 'The certification response could not be confirmed.',
                    'code': 'certification_response_invalid',
                    'hint': 'Inspect current course progress and saved results before continuing. Work may already be saved; do not repeat a write merely because its response is incomplete.',
                }
        return wrapped
    return decorate
