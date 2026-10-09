"""Authored connected-run assignment, never a learner run or completion receipt."""
import hashlib
from typing import Literal

from pydantic import Field, model_validator

from .attempts import encode
from .outcomes import ContractModel
from .process_case import ProcessReviewGuidance
from .repair_case import SourceAnchor

OUTCOMES = {'multi_step.connected_execution', 'multi_step.intermediate_review', 'multi_step.bounded_reasoning'}
EVIDENCE = {
    'multi_step.connected_execution': {'artifact_revision', 'execution_receipt', 'intermediate_snapshot', 'output_snapshot'},
    'multi_step.intermediate_review': {'intermediate_snapshot', 'artifact_revision', 'learner_decision', 'execution_receipt'},
    'multi_step.bounded_reasoning': {'output_snapshot', 'source_reference', 'learner_decision'},
}
KINDS = {'scope_approval': ('multi_step.connected_execution', 'approve_saved_revision_and_assigned_source'),
         'connection_repair': ('multi_step.intermediate_review', 'compare_connection_and_two_stage_results'),
         'source_review': ('multi_step.bounded_reasoning', 'separate_sourced_facts_and_interpretation')}


class ChainQuestion(ContractModel):
    id: Literal['scope_approval', 'connection_repair', 'source_review']
    outcome_id: str
    response_kind: Literal['approve_saved_revision_and_assigned_source', 'compare_connection_and_two_stage_results',
                           'separate_sourced_facts_and_interpretation']
    phase: Literal['before_execution', 'after_execution']
    prompt: str = Field(min_length=60, max_length=3000)


class AuthoredChainFailure(ContractModel):
    provenance: Literal['authored_flawed_example_not_execution']
    notice: str = Field(min_length=40, max_length=1000)
    routing: str = Field(min_length=100, max_length=3000)
    analysis: str = Field(min_length=100, max_length=3000)
    final_summary: str = Field(min_length=100, max_length=3000)


class SourceExpectation(ContractModel):
    id: str = Field(pattern=r'^[a-z][a-z0-9_]{1,99}$')
    meaning: str = Field(min_length=40, max_length=2000)
    anchors: tuple[SourceAnchor, ...] = Field(min_length=1, max_length=5)


class ControlledFailurePractice(ContractModel):
    provenance: Literal['authored_training_stop_configuration_not_execution']
    failure_stage: Literal['reason']
    failure_boundary: Literal['before_reasoning_provider_after_preserved_extraction']
    notice: str = Field(min_length=100, max_length=2000)
    question: str = Field(min_length=60, max_length=2000)
    retry_policy: Literal['new_separately_approved_internal_run_only']
    assessment_policy: Literal['deterministic_stage_and_recovery_choice_no_prose_credit']


class MultiStepCase(ContractModel):
    schema_version: Literal[1] = 1
    id: str = Field(pattern=r'^[a-z][a-z0-9_-]{1,99}$')
    revision: int = Field(ge=1, strict=True)
    module_id: Literal['multi_step']
    provenance: Literal['authored_connected_workflow_case_not_execution']
    source_filename: Literal['subaward-agreement.pdf']
    source_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    notice: str = Field(min_length=60, max_length=1000)
    task: str = Field(min_length=100, max_length=4000)
    intended_output: str = Field(min_length=60, max_length=2000)
    exclusions: tuple[str, ...] = Field(min_length=3, max_length=10)
    required_stages: tuple[Literal['extract', 'reason', 'format'], ...]
    required_links: tuple[Literal['extract_to_reason', 'reason_to_format'], ...]
    flawed_example: AuthoredChainFailure
    instructions: tuple[str, ...] = Field(min_length=5, max_length=12)
    questions: tuple[ChainQuestion, ...] = Field(min_length=3, max_length=3)
    execution_rule: Literal['one_owned_revision_assigned_source_connected_successful_run_not_aggregate_counts']
    repair_rule: Literal['saved_connection_change_new_owned_execution_compare_intermediate_and_final_results']
    comparison_policy: Literal['actual_original_and_corrected_owned_runs_not_authored_specimen']
    recovery_rule: Literal['preserve_completed_steps_inspect_failed_stage_no_automatic_write_replay']
    scope_policy: Literal['assigned_source_internal_draft_no_integrations_or_staff']
    assistance_policy: Literal['agent_may_draft_learner_approves_revision_and_checks_actual_results']
    assessment_policy: Literal['deterministic_execution_plus_structured_review_no_staff_queue_no_presence_credit']
    review_guidance: tuple[ProcessReviewGuidance, ...] = Field(min_length=3, max_length=3)
    source_expectations: tuple[SourceExpectation, ...] = Field(min_length=3, max_length=10)
    controlled_failure_practice: ControlledFailurePractice | None = None

    @model_validator(mode='after')
    def identities(self):
        if self.revision >= 3 and self.controlled_failure_practice is None:
            raise ValueError('This revision requires the disclosed actual stopped-run practice')
        if (len(self.required_stages) != 3 or set(self.required_stages) != {'extract', 'reason', 'format'}
                or len(self.required_links) != 2 or set(self.required_links) != {'extract_to_reason', 'reason_to_format'}):
            raise ValueError('The assignment requires a connected extract-reason-format chain, not a step count')
        if ({question.id for question in self.questions} != set(KINDS)
                or {guide.outcome_id for guide in self.review_guidance} != OUTCOMES
                or len({item.id for item in self.source_expectations}) != len(self.source_expectations)):
            raise ValueError('Questions, outcome guidance and source expectations require unique complete identities')
        for question in self.questions:
            if ((question.outcome_id, question.response_kind) != KINDS[question.id]
                    or question.phase != ('before_execution' if question.id == 'scope_approval' else 'after_execution')):
                raise ValueError('Approval must precede execution and result checks must follow the actual run')
        return self

    @property
    def digest(self):
        return encode(self.model_dump(mode='json', exclude_none=True))[1]

    def public_definition(self):
        return {**self.model_dump(mode='json', exclude={'review_guidance', 'source_expectations'}, exclude_none=True), 'case_sha256': self.digest}

    def verify_contract(self, contract):
        module = next((module for module in contract.modules if module.module_id == self.module_id), None)
        if module is None or {outcome.id for outcome in module.outcomes} != OUTCOMES:
            raise ValueError('The case must bind every declared Multi-Step Workflows outcome')
        guides = {guide.outcome_id: guide for guide in self.review_guidance}
        for outcome in module.outcomes:
            expected_method = 'deterministic' if outcome.id == 'multi_step.connected_execution' else 'structured_review'
            if (outcome.method != expected_method or set(outcome.evidence) != EVIDENCE[outcome.id]
                    or guides[outcome.id].passing_conditions != outcome.passing_conditions
                    or guides[outcome.id].critical_failures != outcome.critical_failures):
                raise ValueError('The case cannot replace run evidence with prose or weaken the declared rubric')

    def verify_source(self, source_bytes, page_texts):
        if hashlib.sha256(source_bytes).hexdigest() != self.source_sha256:
            raise ValueError('The assigned subaward source changed')
        for expectation in self.source_expectations:
            for anchor in expectation.anchors:
                if (anchor.page > len(page_texts)
                        or ' '.join(anchor.quote.split()) not in ' '.join(page_texts[anchor.page - 1].split())):
                    raise ValueError('A private source expectation has no matching assigned-source anchor')

    def verify_exercise(self, exercise):
        if (exercise.get('documents') != [self.source_filename] or exercise.get('expected_fields') != []
                or exercise.get('expected_values') != {} or exercise.get('star_criteria') != {}
                or exercise.get('assessment_case_id') != self.id or exercise.get('connected_case_sha256') != self.digest
                or exercise.get('assessment_method') != 'authenticated_connected_workflow_run_review'):
            raise ValueError('The exercise must bind the connected case without count-based or aggregate credit')


def load_multi_step_case(package):
    from .catalog import CourseCatalogError
    from .outcomes import package_outcomes
    path = 'connected-cases/multi_step.json'
    if path not in package.manifest.artifacts:
        raise CourseCatalogError('This course has no connected-workflow case')
    try:
        case = MultiStepCase.model_validate(package.json(path))
        case.verify_contract(package_outcomes(package))
        case.verify_exercise(package.json('exercises.json')['multi_step'])
        if package.manifest.artifacts.get('documents/' + case.source_filename) != case.source_sha256:
            raise ValueError('The connected case must bind its exact packaged source')
        return case
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise CourseCatalogError('The packaged connected-workflow case is invalid') from exc
