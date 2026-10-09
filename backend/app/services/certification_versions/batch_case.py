"""Authored bounded batch assignment; never execution or recovery evidence."""
import hashlib
from typing import Literal

from pydantic import Field, model_validator

from .attempts import encode
from .outcomes import ContractModel
from .process_case import ProcessReviewGuidance
from .repair_case import SourceAnchor

FIELDS = ('PI Name', 'Institution', 'Total Budget', 'Research Area', 'Sponsoring Agency')
SOURCES = {f'proposal_{i}': f'proposal-batch-{i}.pdf' for i in range(1, 4)}
EVIDENCE = {
    'batch_processing.assigned_coverage': {'assigned_document_snapshot', 'artifact_revision', 'execution_receipt', 'batch_result_snapshot'},
    'batch_processing.targeted_recovery': {'batch_result_snapshot', 'retry_receipt', 'learner_decision'},
    'batch_processing.resource_choice': {'learner_decision', 'pilot_result_snapshot', 'execution_receipt'},
}
FieldName = Literal['PI Name', 'Institution', 'Total Budget', 'Research Area', 'Sponsoring Agency']
SourceId = Literal['proposal_1', 'proposal_2', 'proposal_3']


class BatchField(ContractModel):
    title: FieldName
    meaning: str = Field(min_length=30, max_length=2000)
    comparison: Literal['person_name', 'usd_amount', 'exact_text']


class BatchSource(ContractModel):
    id: SourceId
    filename: Literal['proposal-batch-1.pdf', 'proposal-batch-2.pdf', 'proposal-batch-3.pdf']
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    coverage: str = Field(min_length=40, max_length=2000)
    source_scope: Literal['complete_assigned_document_not_selected_excerpt']


class BatchExpectation(ContractModel):
    source_id: SourceId
    field: FieldName
    expected_value: str = Field(min_length=1, max_length=1000)
    anchors: tuple[SourceAnchor, ...] = Field(min_length=1, max_length=3)


class BatchQuestion(ContractModel):
    id: Literal['pilot_choice', 'scale_choice', 'recovery_choice', 'batch_review']
    phase: Literal['before_pilot', 'after_checked_pilot_before_batch', 'after_failed_item_before_retry', 'after_recovery']
    prompt: str = Field(min_length=60, max_length=3000)


class BatchCase(ContractModel):
    schema_version: Literal[1] = 1
    id: str = Field(pattern=r'^[a-z][a-z0-9_-]{1,99}$')
    revision: int = Field(ge=1, strict=True)
    module_id: Literal['batch_processing']
    provenance: Literal['authored_batch_assignment_not_pilot_coverage_or_recovery_evidence']
    notice: str = Field(min_length=80, max_length=1500)
    task: str = Field(min_length=100, max_length=4000)
    instructions: tuple[str, ...] = Field(min_length=5, max_length=12)
    exclusions: tuple[str, ...] = Field(min_length=3, max_length=10)
    fields: tuple[BatchField, ...] = Field(min_length=5, max_length=5)
    sources: tuple[BatchSource, ...] = Field(min_length=3, max_length=3)
    pilot_source_ids: tuple[SourceId, ...] = Field(min_length=2, max_length=2)
    pilot_limitations: str = Field(min_length=100, max_length=2000)
    controlled_failure_source_id: Literal['proposal_2']
    controlled_failure_rule: Literal['first_full_batch_item_rejected_before_model_dispatch_retry_requires_explicit_same_item_approval']
    questions: tuple[BatchQuestion, ...] = Field(min_length=4, max_length=4)
    expectations: tuple[BatchExpectation, ...] = Field(min_length=15, max_length=15)
    review_guidance: tuple[ProcessReviewGuidance, ...] = Field(min_length=3, max_length=3)
    coverage_rule: Literal['same_batch_identity_distinct_assigned_document_ids_and_terminal_per_item_receipts_not_counts']
    scaling_rule: Literal['source_checked_complete_pilot_same_captured_revision_models_and_sources_explicit_learner_scope']
    recovery_rule: Literal['exact_confirmed_failed_item_original_batch_and_revision_preserve_completed_receipts_no_implicit_retry']
    resource_rule: Literal['actual_model_scope_and_elapsed_time_unknown_usage_and_price_remain_unknown']
    assessment_policy: Literal['deterministic_coverage_and_source_checks_plus_automatic_review_no_staff_queue_or_count_credit']

    @model_validator(mode='after')
    def coherent(self):
        if (tuple(f.title for f in self.fields) != FIELDS
                or tuple(f.comparison for f in self.fields) != ('person_name', 'exact_text', 'usd_amount', 'exact_text', 'exact_text')):
            raise ValueError('Preserve the five distinct field meanings and comparisons')
        if [(s.id, s.filename) for s in self.sources] != list(SOURCES.items()):
            raise ValueError('All three distinct assigned sources must remain in their original order')
        if self.pilot_source_ids != ('proposal_1', 'proposal_3'):
            raise ValueError('The bounded pilot covers both specified research areas and requested amounts')
        if {(e.source_id, e.field) for e in self.expectations} != {(s, f) for s in SOURCES for f in FIELDS}:
            raise ValueError('Every source and field needs an independently anchored expectation')
        if {q.id: q.phase for q in self.questions} != {
                'pilot_choice': 'before_pilot', 'scale_choice': 'after_checked_pilot_before_batch',
                'recovery_choice': 'after_failed_item_before_retry', 'batch_review': 'after_recovery'}:
            raise ValueError('Pilot, scaling and recovery decisions must occur before their distinct actions')
        if {g.outcome_id for g in self.review_guidance} != set(EVIDENCE):
            raise ValueError('Every required batch outcome needs its original review guidance')
        return self

    @property
    def digest(self):
        return encode(self.model_dump(mode='json'))[1]

    def public_definition(self):
        return {**self.model_dump(mode='json', exclude={'expectations', 'review_guidance'}), 'case_sha256': self.digest}

    def verify_contract(self, contract):
        module = next((m for m in contract.modules if m.module_id == self.module_id), None)
        if module is None or {o.id for o in module.outcomes} != set(EVIDENCE):
            raise ValueError('All three original batch outcomes are required')
        guidance = {g.outcome_id: g for g in self.review_guidance}
        for outcome in module.outcomes:
            method = 'deterministic' if outcome.id.endswith('.assigned_coverage') else 'structured_review'
            if (outcome.method != method or set(outcome.evidence) != EVIDENCE[outcome.id]
                    or guidance[outcome.id].passing_conditions != outcome.passing_conditions
                    or guidance[outcome.id].critical_failures != outcome.critical_failures):
                raise ValueError('Batch evidence, deterministic coverage and review criteria cannot be weakened')

    def verify_source(self, source_id, source_bytes, page_texts):
        source = next((s for s in self.sources if s.id == source_id), None)
        if source is None or hashlib.sha256(source_bytes).hexdigest() != source.sha256:
            raise ValueError('The original assigned batch source changed')
        for expectation in (e for e in self.expectations if e.source_id == source_id):
            if any(a.page > len(page_texts) or ' '.join(a.quote.split()) not in ' '.join(page_texts[a.page - 1].split()) for a in expectation.anchors):
                raise ValueError('A batch expectation has no matching original source anchor')
            token = '$' + f'{int(expectation.expected_value):,}' if expectation.field == 'Total Budget' else expectation.expected_value
            if not any(token in a.quote for a in expectation.anchors):
                raise ValueError('The expected value is not supported by its original source anchor')

    def verify_exercise(self, exercise):
        if (exercise.get('documents') != [s.filename for s in self.sources]
                or exercise.get('assessment_case_id') != self.id or exercise.get('batch_case_sha256') != self.digest
                or exercise.get('assessment_method') != 'authenticated_pilot_batch_inventory_and_targeted_recovery'
                or exercise.get('expected_fields') != list(FIELDS)
                or exercise.get('expected_values') != {} or exercise.get('star_criteria') != {}):
            raise ValueError('The exercise must bind the assigned case without count-based stars or private answers')


def load_batch_case(package):
    from .catalog import CourseCatalogError
    from .outcomes import package_outcomes
    path = 'batch-cases/batch_processing.json'
    if path not in package.manifest.artifacts:
        raise CourseCatalogError('This course has no bounded batch case')
    try:
        case = BatchCase.model_validate(package.json(path))
        case.verify_contract(package_outcomes(package))
        case.verify_exercise(package.json('exercises.json')['batch_processing'])
        if any(package.manifest.artifacts.get('documents/' + s.filename) != s.sha256 for s in case.sources):
            raise ValueError('The case requires all three exact original sources')
        return case
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise CourseCatalogError('The packaged bounded batch case is invalid') from exc
