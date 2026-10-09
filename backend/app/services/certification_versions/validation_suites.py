"""Authenticated source-checked test expectations, distinct from run approval."""
import datetime
from typing import Annotated, Literal

from pydantic import Field, model_validator
from pymongo.errors import DuplicateKeyError

from .attempts import encode
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict
from .lab_execution import LabExecutionRepository
from .lab_inputs import LabInputRepository
from .learner_decisions import LearnerDecisionRepository
from .outcomes import ContractModel
from .repair_case import SourceAnchor
from .validation_case import FIELDS, SOURCES, load_validation_case
from .validation_inputs import ValidationInputRepository

Identity = Annotated[str, Field(pattern=r'^[a-f0-9]{32}$')]
Digest = Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]
PROMPT_ID = 'validation_representative_suite'
MAX_SUITE_BYTES = 10 * 1024 * 1024


class LearnerExpectation(ContractModel):
    source_id: Literal['nsf', 'nih']
    field: Literal['Principal Investigator', 'Total Project Budget', 'Named Co-PI']
    expected_kind: Literal['value', 'explicit_absence']
    expected_value: str | None = Field(max_length=1000)
    source_references: tuple[SourceAnchor, ...] = Field(min_length=1, max_length=3)
    source_reason: str = Field(min_length=20, max_length=3000)

    @model_validator(mode='after')
    def meaningful_expectation(self):
        if (self.expected_kind == 'explicit_absence') != (self.expected_value is None):
            raise ValueError('An explicit absence requires null; a known value requires nonempty text')
        if self.expected_value is not None and not self.expected_value.strip():
            raise ValueError('Empty expected values are not test expectations')
        if len(self.source_reason.strip()) < 20:
            raise ValueError('Explain why the source supports this expected value or absence')
        if len({(a.page, a.quote) for a in self.source_references}) != len(self.source_references):
            raise ValueError('Source references must be distinct')
        return self


class ValidationSuiteRequest(ContractModel):
    request_id: Identity
    input_snapshot_id: Identity
    input_snapshot_sha256: Digest
    case_sha256: Digest
    expectations: tuple[LearnerExpectation, ...] = Field(min_length=6, max_length=6)
    suite_design: str = Field(min_length=40, max_length=8000)
    consent: Literal['save_checked_representative_expectations_before_execution']

    @model_validator(mode='after')
    def full_suite(self):
        if {(e.source_id, e.field) for e in self.expectations} != {(s, f) for s in SOURCES for f in FIELDS}:
            raise ValueError('Include one checked expectation for every required field in both sources')
        if len(self.suite_design.strip()) < 40:
            raise ValueError('Explain representative coverage and its limits before execution')
        return self


def embedded_input(snapshot):
    serialized, digest = encode(snapshot)
    return {**{key: snapshot[key] for key in ('uuid', 'user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256', 'artifact_id')},
            'record_json': serialized, 'record_sha256': digest}


def test_cases(body, snapshot):
    """Full immutable suite by logical field, allowing later instruction repair.

    A quote's presence establishes traceability only. It does not prove that the
    learner interpreted it correctly; private checks and review do that later.
    """
    if (snapshot['uuid'] != body.input_snapshot_id or encode(snapshot)[1] != body.input_snapshot_sha256
            or snapshot['case']['case_sha256'] != body.case_sha256):
        raise EnrollmentConflict('Save expectations against the exact original captured source and extraction')
    by_pair = {(item.source_id, item.field): item for item in body.expectations}
    cases = []
    for source in snapshot['documents']:
        entries = []
        for field in FIELDS:
            entry = by_pair[(source['source_id'], field)]
            if any(anchor.page > len(source['pages'])
                   or ' '.join(anchor.quote.split()) not in ' '.join(source['pages'][anchor.page - 1].split())
                   for anchor in entry.source_references):
                raise EnrollmentConflict('Every expected value needs a reference found on the stated original source page')
            entries.append(entry.model_dump(mode='json'))
        cases.append({'source_id': source['source_id'], 'document_id': source['document_id'],
                      'source_sha256': source['source_sha256'], 'source_text_sha256': encode(source['pages'])[1],
                      'source_scope': 'complete_assigned_document_not_selected_excerpt', 'expectations': entries})
    return cases


class ValidationSuiteRepository(LearnerDecisionRepository):
    @staticmethod
    def decode(raw):
        saved = LearnerDecisionRepository.decode(raw)
        try:
            body = ValidationSuiteRequest.model_validate(saved['submission'])
            snapshot = ValidationInputRepository.decode(saved['input_snapshot'])
            cases = test_cases(body, snapshot)
            if (saved['record_kind'] != PROMPT_ID or saved['prompt_id'] != PROMPT_ID or saved['module_id'] != 'validation_qa'
                    or saved['uuid'] != body.request_id or saved['run_id'] != body.input_snapshot_id
                    or saved['request_sha256'] != encode(body.model_dump(mode='json'))[1]
                    or any(saved[key] != snapshot[key] for key in ('user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256'))
                    or saved['case'] != snapshot['case'] or saved['test_cases'] != cases
                    or saved['suite_sha256'] != encode(cases)[1]
                    or saved['submission_channel'] != 'authenticated_learner_validation_expectations'
                    or saved['execution_authorized'] is not False or saved['credit_awarded'] is not False
                    or saved['source_correctness_verified'] is not False or saved['module_completion_eligible'] is not False):
                raise ValueError('The saved test suite changed its inputs, learner expectations or authority')
            return saved
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise CourseCatalogError('The saved representative suite failed integrity verification') from exc

    async def get(self, user_id, submission_id):
        raw = await self.records.find_one({'uuid': submission_id, 'user_id': user_id, 'module_id': 'validation_qa', 'prompt_id': PROMPT_ID})
        return self.decode(raw) if raw else None

    async def submit(self, operation, body, *, actor_user_id):
        body = ValidationSuiteRequest.model_validate(body)
        if actor_user_id != operation.user_id:
            raise EnrollmentConflict('Test expectations require the authenticated learner')
        identity = {'uuid': body.request_id, 'user_id': actor_user_id, 'enrollment_id': operation.progress.enrollment_id,
            'module_id': 'validation_qa', 'course_version': operation.package.manifest.release_id,
            'manifest_sha256': operation.package.manifest_sha256, 'run_id': body.input_snapshot_id, 'prompt_id': PROMPT_ID}
        lease = LabExecutionRepository.check_operation(operation, identity)
        request = body.model_dump(mode='json')
        request_hash = encode(request)[1]

        def replay(raw):
            saved = self.decode(raw)
            if any(saved[key] != value for key, value in identity.items()) or saved['request_sha256'] != request_hash:
                raise EnrollmentConflict('This suite identity already preserves different expectations or another learner')
            return saved

        await LabInputRepository._check_lease(lease)
        existing = await self.records.find_one({'uuid': body.request_id})
        if existing is not None:
            return replay(existing)
        snapshot = await ValidationInputRepository().get(actor_user_id, body.input_snapshot_id)
        if snapshot is None:
            raise EnrollmentConflict('Select an owned original validation capture')
        LabExecutionRepository.check_operation(operation, snapshot)
        case = load_validation_case(operation.package)
        if body.case_sha256 != case.digest or snapshot['case'] != case.public_definition():
            raise EnrollmentConflict('The source expectations belong to another assignment')
        cases = test_cases(body, snapshot)
        saved = {**identity, 'record_kind': PROMPT_ID, 'request_sha256': request_hash, 'submission': request,
            'case': case.public_definition(), 'input_snapshot': embedded_input(snapshot), 'test_cases': cases,
            'suite_sha256': encode(cases)[1], 'submitted_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'submission_channel': 'authenticated_learner_validation_expectations', 'execution_authorized': False,
            'source_correctness_verified': False, 'credit_awarded': False, 'module_completion_eligible': False}
        serialized, digest = encode(saved)
        if len(serialized.encode()) > MAX_SUITE_BYTES:
            raise EnrollmentConflict('The complete source-checked suite exceeds its storage limit; no evidence was truncated')
        self.decode({**saved, 'record_json': serialized, 'record_sha256': digest})
        await LabInputRepository._check_lease(lease)
        try:
            await self.records.insert_one({**identity, 'request_sha256': request_hash, 'record_json': serialized, 'record_sha256': digest})
        except DuplicateKeyError:
            existing = await self.records.find_one({'uuid': body.request_id})
            if existing is None:
                raise EnrollmentConflict('The test suite reference was claimed by another operation')
            return replay(existing)
        await LabInputRepository._check_lease(lease)
        return saved
