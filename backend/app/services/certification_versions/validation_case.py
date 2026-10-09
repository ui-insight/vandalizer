"""Authored representative validation assignment, never observed test evidence."""
import hashlib
from typing import Literal

from pydantic import Field, model_validator

from .attempts import encode
from .outcomes import ContractModel
from .process_case import ProcessReviewGuidance
from .repair_case import SourceAnchor

EVIDENCE = {
    'validation_qa.representative_tests': {'artifact_revision', 'test_case_snapshot', 'source_reference', 'learner_decision'},
    'validation_qa.repair_and_retest': {'artifact_revision', 'test_case_snapshot', 'validation_receipt', 'learner_decision'},
}
FIELDS = ('Principal Investigator', 'Total Project Budget', 'Named Co-PI')
SOURCES = {'nsf': 'nsf-proposal-alpine-ecology.pdf', 'nih': 'nih-r01-neuroscience.pdf'}


class ValidationField(ContractModel):
    title: Literal['Principal Investigator', 'Total Project Budget', 'Named Co-PI']
    meaning: str = Field(min_length=40, max_length=2000)
    comparison: Literal['person_name', 'usd_amount', 'person_name_or_explicit_absence']


class ValidationSource(ContractModel):
    id: Literal['nsf', 'nih']
    filename: Literal['nsf-proposal-alpine-ecology.pdf', 'nih-r01-neuroscience.pdf']
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    coverage: str = Field(min_length=60, max_length=2000)
    source_scope: Literal['complete_assigned_document_not_selected_excerpt']


class ValidationExpectation(ContractModel):
    source_id: Literal['nsf', 'nih']
    field: Literal['Principal Investigator', 'Total Project Budget', 'Named Co-PI']
    expected_value: str | None
    meaning: str = Field(min_length=40, max_length=2000)
    absence_policy: Literal['required_source_value', 'absent_when_role_not_explicitly_named']
    anchors: tuple[SourceAnchor, ...] = Field(min_length=1, max_length=5)

    @model_validator(mode='after')
    def absence_is_explicit(self):
        if ((self.expected_value is None) != (self.absence_policy == 'absent_when_role_not_explicitly_named')
                or (self.expected_value is not None and not self.expected_value.strip())
                or (self.expected_value is None and (self.source_id, self.field) != ('nih', 'Named Co-PI'))):
            raise ValueError('Only the assigned unnamed NIH Co-PI uses explicit absence; empty expectations never count')
        return self


class ValidationQuestion(ContractModel):
    id: Literal['suite_design', 'repair_review']
    outcome_id: str
    phase: Literal['before_original_run', 'after_complete_retest']
    prompt: str = Field(min_length=60, max_length=3000)


class ValidationCase(ContractModel):
    schema_version: Literal[1] = 1
    id: str = Field(pattern=r'^[a-z][a-z0-9_-]{1,99}$')
    revision: int = Field(ge=1, strict=True)
    module_id: Literal['validation_qa']
    provenance: Literal['authored_validation_assignment_not_observed_failure_or_retest']
    notice: str = Field(min_length=80, max_length=1500)
    task: str = Field(min_length=100, max_length=4000)
    instructions: tuple[str, ...] = Field(min_length=5, max_length=12)
    exclusions: tuple[str, ...] = Field(min_length=3, max_length=10)
    fields: tuple[ValidationField, ...] = Field(min_length=3, max_length=3)
    sources: tuple[ValidationSource, ...] = Field(min_length=2, max_length=2)
    flawed_proposal: str = Field(min_length=100, max_length=4000)
    questions: tuple[ValidationQuestion, ...] = Field(min_length=2, max_length=2)
    expectations: tuple[ValidationExpectation, ...] = Field(min_length=6, max_length=6)
    review_guidance: tuple[ProcessReviewGuidance, ...] = Field(min_length=2, max_length=2)
    suite_rule: Literal['learner_checked_expectations_for_every_field_and_source_preserved_across_revisions']
    execution_rule: Literal['actual_saved_owned_revision_each_required_case_before_and_after_no_historical_badge']
    failure_rule: Literal['observed_value_mismatch_required_technical_failure_is_unavailable_not_learning_failure']
    repair_rule: Literal['same_owned_artifact_changed_revision_same_complete_suite_explicit_approval_no_deleted_failures']
    absence_rule: Literal['explicit_absence_is_tested_even_if_the_product_quality_metric_skips_optional_fields']
    assessment_policy: Literal['automatic_structured_review_with_source_bound_checks_no_staff_queue_or_presence_credit']

    @model_validator(mode='after')
    def coherent(self):
        comparisons = ('person_name', 'usd_amount', 'person_name_or_explicit_absence')
        if tuple(field.title for field in self.fields) != FIELDS or tuple(field.comparison for field in self.fields) != comparisons:
            raise ValueError('The three distinct field meanings and comparisons must be preserved')
        if {source.id: source.filename for source in self.sources} != SOURCES:
            raise ValueError('Both distinct assigned sources are required')
        expected_pairs = {(source, field) for source in SOURCES for field in FIELDS}
        if {(item.source_id, item.field) for item in self.expectations} != expected_pairs:
            raise ValueError('Every source/field combination requires its own expected value and source support')
        questions = {q.id: (q.outcome_id, q.phase) for q in self.questions}
        if questions != {'suite_design': ('validation_qa.representative_tests', 'before_original_run'),
                         'repair_review': ('validation_qa.repair_and_retest', 'after_complete_retest')}:
            raise ValueError('The learner must design the suite before execution and explain the actual retest afterward')
        if {item.outcome_id for item in self.review_guidance} != set(EVIDENCE):
            raise ValueError('Both practical outcomes require separate guidance')
        return self

    @property
    def digest(self):
        return encode(self.model_dump(mode='json'))[1]

    def public_definition(self):
        return {**self.model_dump(mode='json', exclude={'expectations', 'review_guidance'}), 'case_sha256': self.digest}

    def verify_contract(self, contract):
        module = next((m for m in contract.modules if m.module_id == self.module_id), None)
        practical = [o for o in module.outcomes if o.method == 'structured_review'] if module else []
        if {o.id for o in practical} != set(EVIDENCE):
            raise ValueError('The case binds both practical outcomes, separate from the recognition assessment')
        guidance = {item.outcome_id: item for item in self.review_guidance}
        for outcome in practical:
            if (set(outcome.evidence) != EVIDENCE[outcome.id]
                    or guidance[outcome.id].passing_conditions != outcome.passing_conditions
                    or guidance[outcome.id].critical_failures != outcome.critical_failures):
                raise ValueError('Validation guidance cannot weaken required evidence or passing conditions')

    def verify_source(self, source_id, source_bytes, page_texts):
        source = next((s for s in self.sources if s.id == source_id), None)
        if source is None or hashlib.sha256(source_bytes).hexdigest() != source.sha256:
            raise ValueError('The assigned validation source changed')
        for expectation in (item for item in self.expectations if item.source_id == source_id):
            for anchor in expectation.anchors:
                if anchor.page > len(page_texts) or ' '.join(anchor.quote.split()) not in ' '.join(page_texts[anchor.page - 1].split()):
                    raise ValueError('A validation expectation has no matching original source anchor')
            if expectation.expected_value is not None:
                token = expectation.expected_value
                if expectation.field == 'Total Project Budget':
                    token = '$' + f'{int(token):,}'
                if not any(token in anchor.quote for anchor in expectation.anchors):
                    raise ValueError('The expected value is not supported by its authored source anchors')

    def verify_exercise(self, exercise):
        if (exercise.get('documents') != [s.filename for s in self.sources]
                or exercise.get('assessment_case_id') != self.id or exercise.get('validation_case_sha256') != self.digest
                or exercise.get('assessment_method') != 'authenticated_representative_suite_repair_retest'
                or exercise.get('expected_fields') != list(FIELDS)
                or exercise.get('expected_values') != {} or exercise.get('star_criteria') != {}):
            raise ValueError('The exercise must bind the full case without test-count credit or private answer keys')


def load_validation_case(package):
    from .catalog import CourseCatalogError
    from .outcomes import package_outcomes
    path = 'validation-cases/validation_qa.json'
    if path not in package.manifest.artifacts:
        raise CourseCatalogError('This course has no representative validation case')
    try:
        case = ValidationCase.model_validate(package.json(path))
        case.verify_contract(package_outcomes(package))
        case.verify_exercise(package.json('exercises.json')['validation_qa'])
        if any(package.manifest.artifacts.get('documents/' + source.filename) != source.sha256 for source in case.sources):
            raise ValueError('The case requires both exact packaged validation sources')
        return case
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise CourseCatalogError('The packaged representative validation case is invalid') from exc
