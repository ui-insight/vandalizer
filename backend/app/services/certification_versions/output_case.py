"""Authored file inspection/private handoff assignment, never a delivery receipt."""
import hashlib
from typing import Literal

from pydantic import Field, model_validator

from .attempts import encode
from .outcomes import ContractModel
from .process_case import ProcessReviewGuidance
from .repair_case import SourceAnchor

EVIDENCE = {
    'output_delivery.usable_artifact': {'execution_receipt', 'artifact_file_snapshot', 'learner_decision'},
    'output_delivery.release_decision': {'artifact_file_snapshot', 'destination_snapshot', 'learner_decision'},
    'output_delivery.delivery_outcome': {'execution_receipt', 'delivery_receipt', 'learner_decision'},
}
QUESTIONS = {
    'artifact_review': ('output_delivery.usable_artifact', 'after_generation_before_release'),
    'release_decision': ('output_delivery.release_decision', 'after_generation_before_release'),
    'delivery_review': ('output_delivery.delivery_outcome', 'after_delivery_attempt'),
}
REQUIRED_FIELDS = ('Project Title', 'PI Name', 'Reporting Period', 'Accomplishments', 'Publications',
    'Students Trained', 'Year 2 Budget Spent', 'Cumulative Budget Spent', 'Remaining Budget', 'Upcoming Milestones', 'Source References')

SOURCE_CHECK_FIELDS = {'identity': 'Project Title', 'pi': 'PI Name', 'period': 'Reporting Period',
    'publications': 'Publications', 'students': 'Students Trained', 'year2': 'Year 2 Budget Spent',
    'cumulative': 'Cumulative Budget Spent', 'remaining': 'Remaining Budget', 'milestones': 'Upcoming Milestones'}


class OutputQuestion(ContractModel):
    id: Literal['artifact_review', 'release_decision', 'delivery_review']
    outcome_id: str
    phase: Literal['after_generation_before_release', 'after_delivery_attempt']
    prompt: str = Field(min_length=60, max_length=3000)


class OutputArtifactRequirement(ContractModel):
    id: Literal['readable_report', 'structured_summary']
    file_type: Literal['pdf', 'csv']
    purpose: str = Field(min_length=50, max_length=1000)
    required_fields: tuple[str, ...]


class OutputSourceCheck(ContractModel):
    id: str = Field(pattern=r'^[a-z][a-z0-9_]{1,99}$')
    field: str
    interpretation: str = Field(min_length=30, max_length=2000)
    anchors: tuple[SourceAnchor, ...] = Field(min_length=1, max_length=5)


class OutputDestination(ContractModel):
    id: Literal['private_training_inbox']
    audience: Literal['enrolled_learner_only']
    data_scope: Literal['approved_generated_files_only']
    description: str = Field(min_length=80, max_length=1500)
    first_attempt: Literal['controlled_rejection_before_destination_write']
    recovery: Literal['explicit_retry_same_approved_bytes_after_failed_receipt']


class OutputDeliveryCase(ContractModel):
    schema_version: Literal[1] = 1
    id: str = Field(pattern=r'^[a-z][a-z0-9_-]{1,99}$')
    revision: int = Field(ge=1, strict=True)
    module_id: Literal['output_delivery']
    provenance: Literal['authored_output_handoff_case_not_generation_or_delivery']
    source_filename: Literal['progress-report-year2.pdf']
    source_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    notice: str = Field(min_length=80, max_length=1500)
    task: str = Field(min_length=100, max_length=4000)
    instructions: tuple[str, ...] = Field(min_length=5, max_length=12)
    exclusions: tuple[str, ...] = Field(min_length=3, max_length=10)
    flawed_proposal: str = Field(min_length=100, max_length=4000)
    questions: tuple[OutputQuestion, ...] = Field(min_length=3, max_length=3)
    artifacts: tuple[OutputArtifactRequirement, ...] = Field(min_length=2, max_length=2)
    destination: OutputDestination
    bundle_rule: Literal['actual_marked_step_download_bundle_inspect_every_member_no_package_builder']
    artifact_rule: Literal['actual_owned_run_bytes_opened_and_compared_not_filename_or_node_count']
    release_rule: Literal['explicit_exact_artifact_destination_audience_scope_approval_before_write']
    delivery_rule: Literal['generation_and_attempt_and_confirmed_write_are_distinct_no_blind_reruns']
    assessment_policy: Literal['automatic_structured_review_no_staff_queue_or_presence_credit']
    source_checks: tuple[OutputSourceCheck, ...] = Field(min_length=5, max_length=12)
    review_guidance: tuple[ProcessReviewGuidance, ...] = Field(min_length=3, max_length=3)

    @model_validator(mode='after')
    def coherent_case(self):
        if ({q.id for q in self.questions} != set(QUESTIONS)
                or any((q.outcome_id, q.phase) != QUESTIONS[q.id] for q in self.questions)
                or {g.outcome_id for g in self.review_guidance} != set(EVIDENCE)):
            raise ValueError('File/release inspection must precede delivery and each outcome requires its own review')
        formats = {a.id: a.file_type for a in self.artifacts}
        if formats != {'readable_report': 'pdf', 'structured_summary': 'csv'}:
            raise ValueError('The assignment requires both an opened report and an actual tabular export')
        if any(a.required_fields != REQUIRED_FIELDS for a in self.artifacts):
            raise ValueError('Both files must preserve the full assignment, distinct periods and source references')
        if (len({c.id for c in self.source_checks}) != len(self.source_checks)
                or {c.id: c.field for c in self.source_checks} != SOURCE_CHECK_FIELDS):
            raise ValueError('Source checks require unique identities and assigned fields')
        return self

    @property
    def digest(self):
        return encode(self.model_dump(mode='json'))[1]

    def public_definition(self):
        return {**self.model_dump(mode='json', exclude={'source_checks', 'review_guidance'}), 'case_sha256': self.digest}

    def verify_contract(self, contract):
        module = next((m for m in contract.modules if m.module_id == self.module_id), None)
        if module is None or {o.id for o in module.outcomes} != set(EVIDENCE):
            raise ValueError('The case must bind all three exact Output and Delivery outcomes')
        guidance = {g.outcome_id: g for g in self.review_guidance}
        for outcome in module.outcomes:
            if (outcome.method != 'structured_review' or set(outcome.evidence) != EVIDENCE[outcome.id]
                    or guidance[outcome.id].passing_conditions != outcome.passing_conditions
                    or guidance[outcome.id].critical_failures != outcome.critical_failures):
                raise ValueError('Authored guidance cannot replace evidence or weaken the outcome rubric')

    def verify_source(self, source_bytes, page_texts):
        if hashlib.sha256(source_bytes).hexdigest() != self.source_sha256:
            raise ValueError('The assigned progress report changed')
        for check in self.source_checks:
            for anchor in check.anchors:
                if anchor.page > len(page_texts) or ' '.join(anchor.quote.split()) not in ' '.join(page_texts[anchor.page - 1].split()):
                    raise ValueError('An authored file-review expectation lacks its original source anchor')

    def verify_exercise(self, exercise):
        if (exercise.get('documents') != [self.source_filename] or exercise.get('expected_fields') != []
                or exercise.get('expected_values') != {} or exercise.get('star_criteria') != {}
                or exercise.get('assessment_case_id') != self.id or exercise.get('output_case_sha256') != self.digest
                or exercise.get('assessment_method') != 'authenticated_artifact_release_delivery_review'):
            raise ValueError('The exercise must bind this exact case without file-count or reflection-presence credit')


def load_output_case(package):
    from .catalog import CourseCatalogError
    from .outcomes import package_outcomes
    path = 'output-cases/output_delivery.json'
    if path not in package.manifest.artifacts:
        raise CourseCatalogError('This course has no Output and Delivery case')
    try:
        case = OutputDeliveryCase.model_validate(package.json(path))
        case.verify_contract(package_outcomes(package))
        case.verify_exercise(package.json('exercises.json')['output_delivery'])
        if package.manifest.artifacts.get('documents/' + case.source_filename) != case.source_sha256:
            raise ValueError('The case must bind its exact packaged source')
        return case
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise CourseCatalogError('The packaged Output and Delivery case is invalid') from exc
