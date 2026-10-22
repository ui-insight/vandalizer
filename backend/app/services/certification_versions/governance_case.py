"""Authored supervision capstone; no assumed learner decisions or delivery."""
import hashlib
from typing import Literal

from pydantic import Field, model_validator

from .attempts import encode
from .outcomes import ContractModel
from .process_case import ProcessReviewGuidance
from .repair_case import SourceAnchor

FIELDS = ('Award ID', 'Project Title', 'Principal Investigator', 'Funds Obligated to Date', 'Approved Project Ceiling', 'Project End Date')
SOURCES = {'award': 'capstone-award-notice.pdf', 'amendment': 'capstone-award-amendment.pdf'}
EVIDENCE = {
    'governance.accountable_handoff': {'artifact_revision', 'handoff_snapshot', 'validation_receipt', 'learner_decision'},
    'governance.capstone_supervision': {'capstone_attempt', 'learner_decision', 'source_reference', 'execution_receipt', 'delivery_receipt'},
}
QUESTIONS = {'scope_correction': 'before_original_execution', 'source_review': 'after_original_before_repair',
             'release_review': 'after_checked_repair_before_handoff', 'final_supervision': 'after_confirmed_private_handoff'}
FieldName = Literal['Award ID', 'Project Title', 'Principal Investigator', 'Funds Obligated to Date', 'Approved Project Ceiling', 'Project End Date']


class GovernanceField(ContractModel):
    title: FieldName
    meaning: str = Field(min_length=30, max_length=2000)
    comparison: Literal['exact_text', 'person_name', 'usd_amount', 'iso_date']


class GovernanceSource(ContractModel):
    id: Literal['award', 'amendment']
    filename: Literal['capstone-award-notice.pdf', 'capstone-award-amendment.pdf']
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    coverage: str = Field(min_length=50, max_length=2000)
    source_scope: Literal['complete_assigned_document_not_selected_excerpt']


class GovernanceAnchor(SourceAnchor):
    source_id: Literal['award', 'amendment']


class GovernanceExpectation(ContractModel):
    field: FieldName
    expected_value: str = Field(min_length=1, max_length=1000)
    anchors: tuple[GovernanceAnchor, ...] = Field(min_length=1, max_length=4)


class GovernanceQuestion(ContractModel):
    id: Literal['scope_correction', 'source_review', 'release_review', 'final_supervision']
    phase: Literal['before_original_execution', 'after_original_before_repair', 'after_checked_repair_before_handoff', 'after_confirmed_private_handoff']
    prompt: str = Field(min_length=60, max_length=4000)


class GovernanceCase(ContractModel):
    schema_version: Literal[1] = 1
    id: str = Field(pattern=r'^[a-z][a-z0-9_-]{1,99}$')
    revision: int = Field(ge=1, strict=True)
    module_id: Literal['governance']
    provenance: Literal['authored_supervision_case_not_learner_approval_or_delivery']
    task_as_of: Literal['2027-01-05']
    notice: str = Field(min_length=80, max_length=2000)
    task: str = Field(min_length=100, max_length=4000)
    instructions: tuple[str, ...] = Field(min_length=6, max_length=12)
    exclusions: tuple[str, ...] = Field(min_length=3, max_length=10)
    flawed_proposal: str = Field(min_length=100, max_length=4000)
    original_field_flaw: str = Field(min_length=60, max_length=2000)
    fields: tuple[GovernanceField, ...] = Field(min_length=6, max_length=6)
    sources: tuple[GovernanceSource, ...] = Field(min_length=2, max_length=2)
    expectations: tuple[GovernanceExpectation, ...] = Field(min_length=6, max_length=6)
    questions: tuple[GovernanceQuestion, ...] = Field(min_length=4, max_length=4)
    review_guidance: tuple[ProcessReviewGuidance, ...] = Field(min_length=2, max_length=2)
    artifact_rule: Literal['same_owned_six_field_extraction_actual_original_failure_and_changed_revision_retest']
    source_rule: Literal['both_complete_original_records_jointly_consumed_issued_amendment_controls_changed_fields']
    scope_rule: Literal['authenticated_learner_corrects_flawed_scope_before_exact_internal_run_no_external_or_ongoing_authority']
    handoff_rule: Literal['exact_checked_results_and_learner_owned_accountability_memo_private_json_bytes']
    delivery_rule: Literal['disclosed_first_attempt_rejection_before_write_explicit_retry_same_approved_bytes']
    assessment_policy: Literal['automatic_source_veto_and_learner_decision_review_no_staff_queue_or_sharing_credit']

    @model_validator(mode='after')
    def coherent(self):
        if tuple(f.title for f in self.fields) != FIELDS or tuple(e.field for e in self.expectations) != FIELDS:
            raise ValueError('The capstone must preserve all six distinct source-grounded fields')
        if ({s.id: s.filename for s in self.sources} != SOURCES or len({s.sha256 for s in self.sources}) != 2
                or tuple(s.id for s in self.sources) != ('award', 'amendment')):
            raise ValueError('The capstone requires both distinct complete original records in fixed order')
        if ({q.id: q.phase for q in self.questions} != QUESTIONS or {g.outcome_id for g in self.review_guidance} != set(EVIDENCE)):
            raise ValueError('Scope, source, release and final decisions require their own authenticated phase')
        kinds = {f.title: f.comparison for f in self.fields}
        if kinds != {field: 'usd_amount' if field in ('Funds Obligated to Date', 'Approved Project Ceiling')
                     else 'person_name' if field == 'Principal Investigator' else 'iso_date' if field == 'Project End Date' else 'exact_text' for field in FIELDS}:
            raise ValueError('Do not replace amount, identity or date semantics with loose text matching')
        if not all(any(a.source_id == 'amendment' for a in e.anchors) for e in self.expectations if e.field in ('Funds Obligated to Date', 'Project End Date')):
            raise ValueError('Changed funding and end date require the issued amendment as evidence')
        return self

    @property
    def digest(self):
        return encode(self.model_dump(mode='json'))[1]

    def public_definition(self):
        return {**self.model_dump(mode='json', exclude={'expectations', 'review_guidance'}), 'case_sha256': self.digest}

    def verify_contract(self, contract):
        module = next((m for m in contract.modules if m.module_id == 'governance'), None)
        practical = [o for o in module.outcomes if o.method == 'structured_review'] if module else []
        if {o.id for o in practical} != set(EVIDENCE):
            raise ValueError('Bind both Governance practical outcomes; preserve recognition separately')
        guidance = {g.outcome_id: g for g in self.review_guidance}
        for outcome in practical:
            if (set(outcome.evidence) != EVIDENCE[outcome.id]
                    or guidance[outcome.id].passing_conditions != outcome.passing_conditions
                    or guidance[outcome.id].critical_failures != outcome.critical_failures):
                raise ValueError('Authored guidance cannot weaken or replace the original rubric')

    def verify_source(self, source_id, source_bytes, pages):
        source = next((s for s in self.sources if s.id == source_id), None)
        if source is None or hashlib.sha256(source_bytes).hexdigest() != source.sha256:
            raise ValueError('The assigned complete capstone source changed')
        for expectation in self.expectations:
            for anchor in expectation.anchors:
                if anchor.source_id == source_id and (anchor.page > len(pages)
                        or ' '.join(anchor.quote.split()) not in ' '.join(pages[anchor.page - 1].split())):
                    raise ValueError('A source-grounded field lost its original page anchor')

    def verify_exercise(self, exercise):
        if (exercise.get('documents') != [s.filename for s in self.sources] or exercise.get('expected_fields') != list(FIELDS)
                or exercise.get('expected_values') != {} or exercise.get('star_criteria') != {}
                or exercise.get('assessment_case_id') != self.id or exercise.get('governance_case_sha256') != self.digest
                or exercise.get('assessment_method') != 'authenticated_bounded_supervision_and_private_handoff'):
            raise ValueError('Bind this exact assignment without broad-sharing, staff-availability or presence credit')


def load_governance_case(package):
    from .catalog import CourseCatalogError
    from .outcomes import package_outcomes
    path = 'governance-cases/governance.json'
    if path not in package.manifest.artifacts:
        raise CourseCatalogError('This course has no bounded Governance capstone')
    try:
        case = GovernanceCase.model_validate(package.json(path))
        case.verify_contract(package_outcomes(package))
        case.verify_exercise(package.json('exercises.json')['governance'])
        if any(package.manifest.artifacts.get('documents/' + s.filename) != s.sha256 for s in case.sources):
            raise ValueError('Each capstone source must bind its exact packaged PDF')
        return case
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise CourseCatalogError('The packaged Governance capstone is invalid') from exc
