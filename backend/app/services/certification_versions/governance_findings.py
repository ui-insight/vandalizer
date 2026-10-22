"""Preserve the learner's source finding after actual failure and before repair capture."""
import datetime
from typing import Literal

from pydantic import Field, model_validator
from pymongo.errors import DuplicateKeyError

from .attempts import encode
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict
from .governance_case import GovernanceCase, load_governance_case
from .governance_checks import canonical, check_result
from .governance_scope import Digest, Identity
from .lab_execution import LabExecutionRepository
from .lab_inputs import LabInputRepository
from .learner_decisions import LearnerDecisionRepository
from .outcomes import ContractModel

PROMPT_ID = 'governance_original_source_finding'
MAX_FINDING_BYTES = 12 * 1024 * 1024


class GovernanceSourceQuote(ContractModel):
    source_id: Literal['award', 'amendment']
    page: int = Field(strict=True, ge=1, le=100)
    quote: str = Field(min_length=10, max_length=2000)


class GovernanceFindingRequest(ContractModel):
    request_id: Identity
    run_id: Identity
    result_sha256: Digest
    case_sha256: Digest
    field: Literal['Funds Obligated to Date']
    observed_value: str = Field(min_length=1, max_length=2000)
    source_references: tuple[GovernanceSourceQuote, ...] = Field(min_length=2, max_length=6)
    explanation: str = Field(min_length=40, max_length=8000)
    consent: Literal['save_my_original_source_finding_before_repair']

    @model_validator(mode='after')
    def original_sources(self):
        if (len(self.explanation.strip()) < 40 or {q.source_id for q in self.source_references} != {'award', 'amendment'}
                or len({(q.source_id, q.page, q.quote) for q in self.source_references}) != len(self.source_references)):
            raise ValueError('Explain the observed funding failure with distinct quotes from both original records')
        return self


def embedded_execution(run):
    from .governance_preparation import GovernancePreparation
    plan = run['plan']
    raw = {key: plan[key] for key in ('uuid', 'user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256', 'input_snapshot_id')}
    raw.update(state=run['state'], scope_decision_id=run['scope_decision_id'], scope_decision_sha256=run['scope_decision_sha256'])
    for value, prefix in ((plan, 'plan'), (run['authorization'], 'authorization'), (run['result'], 'result'), (run['extraction_events'], 'extraction_events')):
        if value is not None:
            raw[prefix + '_json'], raw[prefix + '_sha256'] = encode(value)
    raw['extraction_event_count'] = len(run['extraction_events'])
    if raw['plan_sha256'] != run['plan_sha256'] or GovernancePreparation.decode(raw) != run:
        raise CourseCatalogError('The capstone execution could not be preserved exactly')
    return raw


def validate_finding(body, run):
    if (run['state'] != 'completed' or run['plan']['phase'] != 'original' or body.run_id != run['run_id']
            or body.result_sha256 != encode(run['result'])[1] or body.case_sha256 != run['plan']['case_sha256']):
        raise EnrollmentConflict('Inspect the exact owned original completed extraction before recording its finding')
    snapshot = run['plan']['input_snapshot']
    case = GovernanceCase.model_validate(snapshot['authored_case'])
    checks = check_result(case, snapshot, run['result']['extraction'], run_id=run['run_id'], phase='original')
    field = next(f for f in checks['fields'] if f['field'] == body.field)
    if (not checks['complete'] or field['status'] != 'revision_required'
            or canonical(body.observed_value, 'usd_amount') != canonical(field['actual_value'], 'usd_amount')):
        raise EnrollmentConflict('A finding requires the actual comparable unsupported funding value, not a missing value or invented failure')
    sources = {s['source_id']: s for s in snapshot['documents']}
    for quote in body.source_references:
        pages = sources[quote.source_id]['pages']
        if quote.page > len(pages) or ' '.join(quote.quote.split()) not in ' '.join(pages[quote.page - 1].split()):
            raise EnrollmentConflict('Each quote must occur on the specified page of its complete original source')
    return checks


class GovernanceFindingRepository(LearnerDecisionRepository):
    @staticmethod
    def decode(raw):
        from .governance_preparation import GovernancePreparation
        saved = LearnerDecisionRepository.decode(raw)
        try:
            body = GovernanceFindingRequest.model_validate(saved['submission'])
            # Reject recursive repair chains before invoking their decoder.
            import json
            if json.loads(saved['execution']['plan_json'])['phase'] != 'original':
                raise ValueError('Findings preserve an original diagnostic run, never a repair chain')
            run = GovernancePreparation.decode(saved['execution'])
            checks = validate_finding(body, run)
            if (saved['record_kind'] != PROMPT_ID or saved['prompt_id'] != PROMPT_ID or saved['module_id'] != 'governance'
                    or saved['uuid'] != body.request_id or saved['run_id'] != run['run_id']
                    or saved['case'] != run['plan']['input_snapshot']['case'] or saved['checks'] != checks
                    or saved['prompt'] != next(q for q in saved['case']['questions'] if q['id'] == 'source_review')
                    or saved['request_sha256'] != encode(body.model_dump(mode='json'))[1]
                    or any(saved[key] != run['plan'][key] for key in ('user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256'))
                    or saved['submission_channel'] != 'authenticated_learner_governance_source_finding'
                    or datetime.datetime.fromisoformat(saved['submitted_at']).tzinfo is None
                    or any(saved[k] is not False for k in ('execution_authorized', 'external_effects_authorized', 'credit_awarded', 'module_completion_eligible'))):
                raise ValueError('The source finding changed its actor, original result, exact evidence or authority')
            return saved
        except (KeyError, TypeError, ValueError, StopIteration) as exc:
            raise CourseCatalogError('The saved Governance source finding failed integrity verification') from exc

    async def get(self, user_id, reference):
        raw = await self.records.find_one({'uuid': reference, 'user_id': user_id, 'module_id': 'governance', 'prompt_id': PROMPT_ID})
        return self.decode(raw) if raw else None

    async def submit(self, operation, body, *, actor_user_id):
        from .governance_preparation import GovernancePreparation
        body = GovernanceFindingRequest.model_validate(body)
        if actor_user_id != operation.user_id:
            raise EnrollmentConflict('Only the authenticated learner can record this source finding')
        identity = {'uuid': body.request_id, 'user_id': actor_user_id, 'enrollment_id': operation.progress.enrollment_id,
            'module_id': 'governance', 'course_version': operation.package.manifest.release_id, 'manifest_sha256': operation.package.manifest_sha256,
            'run_id': body.run_id, 'prompt_id': PROMPT_ID}
        lease = LabExecutionRepository.check_operation(operation, identity)
        request = body.model_dump(mode='json')
        request_hash = encode(request)[1]

        def replay(raw):
            if any(raw.get(k) != v for k, v in identity.items()) or raw.get('request_sha256') != request_hash:
                raise EnrollmentConflict('This finding identity belongs to a different learner, answer or original result')
            return self.decode(raw)

        await LabInputRepository._check_lease(lease)
        existing = await self.records.find_one({'uuid': body.request_id})
        if existing is not None:
            return replay(existing)
        run = await GovernancePreparation().get(actor_user_id, body.run_id)
        if run is None:
            raise EnrollmentConflict('The original owned extraction is unavailable')
        LabExecutionRepository.check_operation(operation, run['plan'])
        case = load_governance_case(operation.package)
        if body.case_sha256 != case.digest:
            raise EnrollmentConflict('The finding must belong to the assigned capstone')
        saved = {**identity, 'record_kind': PROMPT_ID, 'request_sha256': request_hash, 'submission': request,
            'case': case.public_definition(), 'checks': validate_finding(body, run), 'execution': embedded_execution(run),
            'prompt': next(q.model_dump(mode='json') for q in case.questions if q.id == 'source_review'),
            'submitted_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'submission_channel': 'authenticated_learner_governance_source_finding', 'execution_authorized': False,
            'external_effects_authorized': False, 'credit_awarded': False, 'module_completion_eligible': False}
        serialized, digest = encode(saved)
        if len(serialized.encode()) > MAX_FINDING_BYTES:
            raise EnrollmentConflict('The complete finding exceeds its storage limit; no original evidence was truncated')
        self.decode({**identity, 'request_sha256': request_hash, 'record_json': serialized, 'record_sha256': digest})
        await LabInputRepository._check_lease(lease)
        try:
            await self.records.insert_one({**identity, 'request_sha256': request_hash, 'record_json': serialized, 'record_sha256': digest})
        except DuplicateKeyError:
            existing = await self.records.find_one({'uuid': body.request_id})
            if existing is None:
                raise EnrollmentConflict('This finding identity was claimed by another operation')
            return replay(existing)
        await LabInputRepository._check_lease(lease)
        return saved
