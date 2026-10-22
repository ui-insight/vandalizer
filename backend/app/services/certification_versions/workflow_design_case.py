"""Versioned Workflow Design assignment; neither an artifact nor a result.

The supplied map is explicitly authored. A learner map must later be loaded
from its owned immutable submission, and a design from a saved workspace
workflow. Prose supplied by the client is not a substitute for either record.
"""
from typing import Literal

from pydantic import Field, model_validator

from .attempts import encode
from .outcomes import ContractModel
from .process_case import ProcessInput, ProcessReviewGuidance

OUTCOMES = {'workflow_design.data_flow', 'workflow_design.approval_boundary', 'workflow_design.reviewable_design'}
KINDS = {'data_flow': 'trace_saved_configuration', 'approval_boundary': 'correct_then_approve_design',
         'reviewable_design': 'explain_review_and_stop_path'}


class DesignQuestion(ContractModel):
    id: Literal['data_flow', 'approval_boundary', 'reviewable_design']
    outcome_id: str
    prompt: str = Field(min_length=40, max_length=3000)
    response_kind: Literal['trace_saved_configuration', 'correct_then_approve_design', 'explain_review_and_stop_path']


class SuppliedProcessMap(ContractModel):
    id: str = Field(pattern=r'^[a-z][a-z0-9_-]{1,99}$')
    provenance: Literal['authored_example_not_learner_work']
    method_and_rationale: str = Field(min_length=60, max_length=3000)
    ordered_process_map: str = Field(min_length=100, max_length=5000)
    bounded_task_brief: str = Field(min_length=100, max_length=3000)


class WorkflowDesignCase(ContractModel):
    schema_version: Literal[1] = 1
    id: str = Field(pattern=r'^[a-z][a-z0-9_-]{1,99}$')
    revision: int = Field(ge=1, strict=True)
    module_id: Literal['workflow_design']
    provenance: Literal['authored_workflow_design_case_not_execution']
    notice: str = Field(min_length=40, max_length=1000)
    task: str = Field(min_length=100, max_length=4000)
    source_process_case_id: str
    source_process_case_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    assigned_inputs: tuple[ProcessInput, ...] = Field(min_length=1, max_length=10)
    intended_output: str = Field(min_length=30, max_length=2000)
    exclusions: tuple[str, ...] = Field(min_length=1, max_length=10)
    handoff_choices: tuple[Literal['owned_saved_process_submission', 'supplied_example'], ...]
    handoff_policy: Literal['explicit_choice_freeze_original_no_credit_transfer']
    supplied_map: SuppliedProcessMap
    flawed_proposal: str = Field(min_length=100, max_length=5000)
    configuration_instructions: tuple[str, ...] = Field(min_length=3, max_length=12)
    questions: tuple[DesignQuestion, ...] = Field(min_length=3, max_length=3)
    artifact_policy: Literal['owned_saved_workflow_snapshot_not_reflection_or_step_count']
    assistance_policy: Literal['agent_may_draft_learner_must_inspect_correct_and_approve_saved_revision']
    execution_policy: Literal['design_only_no_run_send_share_or_staff_request']
    assessment_policy: Literal['automatic_structured_review_no_staff_queue_no_presence_credit']
    review_guidance: tuple[ProcessReviewGuidance, ...] = Field(min_length=3, max_length=3)

    @model_validator(mode='after')
    def validate_identities(self):
        if (set(self.handoff_choices) != {'owned_saved_process_submission', 'supplied_example'}
                or len(self.handoff_choices) != 2):
            raise ValueError('The learner must be able to choose an owned original map or the supplied example')
        if len({item.id for item in self.assigned_inputs}) != len(self.assigned_inputs):
            raise ValueError('Assigned inputs require unique identities')
        if ({question.id for question in self.questions} != set(KINDS)
                or {guide.outcome_id for guide in self.review_guidance} != OUTCOMES):
            raise ValueError('Every Workflow Design outcome needs exactly one question and review guide')
        if any(question.outcome_id != f'workflow_design.{question.id}'
               or question.response_kind != KINDS[question.id] for question in self.questions):
            raise ValueError('Each question must bind its declared outcome and evidence response')
        return self

    @property
    def digest(self):
        return encode(self.model_dump(mode='json'))[1]

    def public_definition(self):
        return {**self.model_dump(mode='json', exclude={'review_guidance'}), 'case_sha256': self.digest}

    def verify_process_case(self, process):
        if (self.source_process_case_id != process.id or self.source_process_case_sha256 != process.digest
                or self.assigned_inputs != process.assigned_inputs or self.intended_output != process.intended_output
                or self.exclusions != process.exclusions):
            raise ValueError('Workflow Design must preserve its exact source process case and scope')

    def verify_contract(self, contract):
        module = next((module for module in contract.modules if module.module_id == self.module_id), None)
        if module is None or {outcome.id for outcome in module.outcomes} != OUTCOMES:
            raise ValueError('Workflow Design must cover the exact declared outcomes')
        guides = {guide.outcome_id: guide for guide in self.review_guidance}
        evidence = {'data_flow': {'artifact_revision', 'design_snapshot', 'learner_decision'},
                    'approval_boundary': {'proposal_snapshot', 'artifact_revision', 'learner_decision'},
                    'reviewable_design': {'design_snapshot', 'learner_decision'}}
        for outcome in module.outcomes:
            guide = guides[outcome.id]
            if (outcome.method != 'structured_review' or guide.passing_conditions != outcome.passing_conditions
                    or guide.critical_failures != outcome.critical_failures
                    or set(outcome.evidence) != evidence[outcome.id.split('.')[1]]):
                raise ValueError('Design guidance cannot weaken the rubric or replace artifact evidence with prose')

    def verify_exercise(self, exercise):
        if (exercise.get('documents') != [] or exercise.get('expected_fields') != []
                or exercise.get('expected_values') != {} or exercise.get('star_criteria') != {}
                or exercise.get('assessment_case_id') != self.id or exercise.get('design_case_sha256') != self.digest
                or exercise.get('assessment_method') != 'authenticated_saved_workflow_design_review'):
            raise ValueError('The design exercise must bind its case without reflection or step-count credit')


def load_workflow_design_case(package):
    from .catalog import CourseCatalogError
    from .outcomes import package_outcomes
    from .process_case import load_process_case
    path = 'design-cases/workflow_design.json'
    if path not in package.manifest.artifacts:
        raise CourseCatalogError('This course has no Workflow Design case')
    try:
        case = WorkflowDesignCase.model_validate(package.json(path))
        case.verify_contract(package_outcomes(package))
        case.verify_process_case(load_process_case(package))
        case.verify_exercise(package.json('exercises.json')['workflow_design'])
        return case
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise CourseCatalogError('The packaged Workflow Design case is invalid') from exc
