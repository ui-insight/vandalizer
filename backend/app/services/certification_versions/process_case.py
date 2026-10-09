"""Authored process-design task, not learner evidence or a grading result.

Keep the flawed proposal, learner-facing questions and private review guidance
versioned together. Authenticated submission, saved-map handoff and assessment
are separate delivery work; validating this case awards nothing.
"""
from typing import Literal

from pydantic import Field, model_validator

from .attempts import encode
from .outcomes import ContractModel

OUTCOMES = {'process_mapping.method_choice', 'process_mapping.human_checkpoint', 'process_mapping.bounded_scope'}


class ProcessInput(ContractModel):
    id: str = Field(pattern=r'^[a-z][a-z0-9_-]{1,99}$')
    description: str = Field(min_length=20, max_length=1500)


class MethodComparison(ContractModel):
    id: str = Field(pattern=r'^[a-z][a-z0-9_-]{1,99}$')
    situation: str = Field(min_length=30, max_length=1500)


class ProcessQuestion(ContractModel):
    id: str = Field(pattern=r'^[a-z][a-z0-9_]{1,99}$')
    outcome_id: str
    prompt: str = Field(min_length=30, max_length=3000)
    response_kind: Literal['method_and_rationale', 'ordered_process_map', 'bounded_task_brief']


class ProcessReviewGuidance(ContractModel):
    outcome_id: str
    passing_conditions: tuple[str, ...] = Field(min_length=1)
    critical_failures: tuple[str, ...] = Field(min_length=1)
    case_application: str = Field(min_length=50, max_length=3000)


class ProcessMappingCase(ContractModel):
    schema_version: Literal[1] = 1
    id: str = Field(pattern=r'^[a-z][a-z0-9_-]{1,99}$')
    revision: int = Field(ge=1, strict=True)
    module_id: Literal['process_mapping']
    provenance: Literal['authored_fictional_design_case_not_execution']
    notice: str = Field(min_length=40, max_length=1000)
    task: str = Field(min_length=100, max_length=4000)
    assigned_inputs: tuple[ProcessInput, ...] = Field(min_length=1, max_length=10)
    intended_output: str = Field(min_length=30, max_length=2000)
    repetition: str = Field(min_length=20, max_length=1000)
    authority: str = Field(min_length=40, max_length=2000)
    exclusions: tuple[str, ...] = Field(min_length=1, max_length=10)
    exception_conditions: tuple[str, ...] = Field(min_length=1, max_length=10)
    flawed_proposal: str = Field(min_length=100, max_length=4000)
    method_comparisons: tuple[MethodComparison, ...] = Field(min_length=3, max_length=3)
    method_options: tuple[Literal['chat', 'project', 'reusable_extraction', 'workflow', 'automation'], ...]
    questions: tuple[ProcessQuestion, ...] = Field(min_length=3, max_length=3)
    assistance_policy: Literal['agent_may_draft_learner_must_review_correct_and_submit']
    assessment_policy: Literal['automatic_structured_review_no_staff_queue_no_presence_credit']
    handoff_policy: Literal['preserve_original_approved_map_or_choose_provided_example']
    review_guidance: tuple[ProcessReviewGuidance, ...] = Field(min_length=3, max_length=3)

    @model_validator(mode='after')
    def complete_and_unambiguous(self):
        for items in (self.assigned_inputs, self.method_comparisons, self.questions):
            if len({item.id for item in items}) != len(items):
                raise ValueError('Case inputs, comparisons and questions need unique identities')
        if (set(self.method_options) != {'chat', 'project', 'reusable_extraction', 'workflow', 'automation'}
                or len(self.method_options) != 5):
            raise ValueError('The task must permit comparison of all five working methods')
        if ({question.outcome_id for question in self.questions} != OUTCOMES
                or {guidance.outcome_id for guidance in self.review_guidance} != OUTCOMES):
            raise ValueError('Every process-mapping outcome requires exactly one question and private review guide')
        kinds = {'process_mapping.method_choice': 'method_and_rationale',
                 'process_mapping.human_checkpoint': 'ordered_process_map',
                 'process_mapping.bounded_scope': 'bounded_task_brief'}
        if any(question.response_kind != kinds[question.outcome_id] for question in self.questions):
            raise ValueError('Each outcome requires its corresponding decision or map artifact')
        return self

    @property
    def digest(self):
        return encode(self.model_dump(mode='json'))[1]

    def public_definition(self):
        return {**self.model_dump(mode='json', exclude={'review_guidance'}), 'case_sha256': self.digest}

    def verify_contract(self, contract):
        module = next((module for module in contract.modules if module.module_id == self.module_id), None)
        if module is None or {outcome.id for outcome in module.outcomes} != OUTCOMES:
            raise ValueError('Process case must cover the exact declared module outcomes')
        guidance = {item.outcome_id: item for item in self.review_guidance}
        for outcome in module.outcomes:
            review = guidance[outcome.id]
            if (outcome.method != 'structured_review' or review.passing_conditions != outcome.passing_conditions
                    or review.critical_failures != outcome.critical_failures):
                raise ValueError('Case review guidance cannot silently change the outcome rubric')

    def verify_exercise(self, exercise):
        if (exercise.get('documents') != [] or exercise.get('expected_fields') != []
                or exercise.get('expected_values') != {} or exercise.get('star_criteria') != {}
                or exercise.get('assessment_case_id') != self.id or exercise.get('process_case_sha256') != self.digest
                or exercise.get('assessment_method') != 'authenticated_process_map_review'):
            raise ValueError('The process exercise must bind the case without document, field-count or legacy reflection credit')


def load_process_case(package, module_id='process_mapping'):
    from .catalog import CourseCatalogError
    from .outcomes import package_outcomes
    path = f'process-cases/{module_id}.json'
    if path not in package.manifest.artifacts:
        raise CourseCatalogError('This course has no process-design case for the module')
    try:
        case = ProcessMappingCase.model_validate(package.json(path))
        if case.module_id != module_id:
            raise ValueError('Wrong module')
        case.verify_contract(package_outcomes(package))
        case.verify_exercise(package.json('exercises.json')[module_id])
        return case
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise CourseCatalogError('The packaged process-design case is invalid') from exc
