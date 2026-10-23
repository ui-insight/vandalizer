"""Authenticated capstone learner actions, exact downloads and preserved read-only history."""
import base64

from .source_access import owned_source
from app.models.search_set import SearchSet
from app.services.storage import get_storage
from . import practical_preparation
from .attempts import encode
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict, EnrollmentRepository
from .process_delivery import ProcessAssessment
from .runtime import CourseOperation
from .governance_approval import GovernanceApprovalRepository
from .governance_case import load_governance_case
from .governance_execution import GovernanceExecution
from .governance_findings import GovernanceFindingRepository
from .governance_handoff import GovernanceHandoffRepository
from .governance_inputs import GovernanceInputRepository
from .governance_memos import GovernanceMemoRepository
from .governance_preparation import GovernancePreparation
from .governance_recovery import GovernanceRecovery
from .governance_release import GovernanceReleaseRepository
from .governance_reviews import GovernanceReviewRepository
from .governance_scope import GovernanceScopeCorrection


class GovernanceUnavailable(ValueError):
    pass


class GovernanceDelivery:
    def __init__(self, repository=None):
        self.repository = repository or EnrollmentRepository()
        self.inputs, self.runs, self.scopes = GovernanceInputRepository(), GovernanceExecution(), GovernanceApprovalRepository()
        self.corrections, self.findings = GovernanceScopeCorrection(), GovernanceFindingRepository()
        self.memos, self.releases, self.handoffs = GovernanceMemoRepository(), GovernanceReleaseRepository(), GovernanceHandoffRepository()
        self.reviews = GovernanceReviewRepository()

    def repositories(self):
        return {'capture': self.inputs, 'run': self.runs, 'scope': self.scopes, 'correction': self.corrections,
            'finding': self.findings, 'memo': self.memos, 'release': self.releases, 'handoff': self.handoffs, 'review': self.reviews}

    async def course(self, user_id, enrollment_id):
        enrollment = await self.repository._enrollment(user_id, enrollment_id)
        package = self.repository.catalog.load(enrollment.course_version)
        if 'governance-cases/governance.json' not in package.manifest.artifacts:
            raise GovernanceUnavailable('This course does not offer the bounded Governance capstone')
        return enrollment, package, load_governance_case(package)

    @staticmethod
    def verify(record, enrollment, case):
        if (any(record[k] != v for k, v in {'user_id': enrollment.user_id, 'enrollment_id': enrollment.uuid,
                'course_version': enrollment.course_version, 'manifest_sha256': enrollment.manifest_sha256, 'module_id': 'governance'}.items())
                or (record['case_sha256'] != case.digest if 'case_sha256' in record else record['case'] != case.public_definition())):
            raise CourseCatalogError('The saved capstone record differs from its original course')

    async def writable(self, enrollment, enabled):
        selection = await self.repository.selections.find_one({'user_id': enrollment.user_id})
        return bool(enabled and enrollment.state in ('active', 'completed') and selection and selection.get('active_enrollment_id') == enrollment.uuid)

    @staticmethod
    def capture_view(saved):
        return {k: saved[k] for k in ('uuid', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256', 'case',
            'artifact_id', 'artifact_sha256', 'artifact', 'captured_at')} | {
            'documents': [{k: v for k, v in s.items() if k != 'source_pdf_base64'} for s in saved['documents']],
            'input_snapshot_sha256': encode(saved)[1], 'execution_authorized': False, 'credit_awarded': False}

    async def run_view(self, run, *, writable=False):
        plan = run['plan']
        scope = run['authorization']['decision'] if run['authorization'] else None
        if scope is None and run['scope_decision_id']:
            scope = await self.scopes.get(plan['user_id'], run['scope_decision_id'])
        if scope is not None and (scope['run_id'] != run['run_id'] or scope['plan_sha256'] != run['plan_sha256']
                or scope['user_id'] != plan['user_id'] or scope['enrollment_id'] != plan['enrollment_id'] or encode(scope)[1] != run['scope_decision_sha256']):
            raise CourseCatalogError('The current approval differs from this exact capstone plan')
        return {**{k: plan[k] for k in ('enrollment_id', 'module_id', 'course_version', 'manifest_sha256', 'input_snapshot_id',
                    'case_sha256', 'model_names', 'prepared_at', 'phase', 'changed_fields', 'original_run_id', 'original_run_sha256')},
            **{k: run[k] for k in ('run_id', 'state', 'plan_sha256', 'scope_decision_id', 'scope_decision_sha256', 'extraction_events', 'result')},
            'run_sha256': encode(run)[1], 'input_snapshot': self.capture_view(plan['input_snapshot']), 'scope_decision': scope,
            'scope_correction': await self.record_view('correction', plan['scope_correction']),
            'source_finding': await self.record_view('finding', plan['source_finding']) if plan['source_finding'] else None,
            'approval_question': plan['approval_requirement']['question'],
            'authorization_sha256': encode(run['authorization'])[1] if run['authorization'] else None,
            'result_sha256': encode(run['result'])[1] if run['result'] else None, 'extraction_events_sha256': encode(run['extraction_events'])[1],
            'can_save_scope': writable and run['state'] == 'prepared',
            'can_execute': bool(writable and run['state'] == 'prepared' and scope and scope['submission']['choice'] == 'approve'),
            'can_finalize': bool(writable and run['state'] == 'executing' and len(run['extraction_events']) == 2
                and run['extraction_events'][-1]['receipt']['result']['status'] == 'completed'),
            'credit_awarded': False, 'module_completion_eligible': False}

    async def record_view(self, kind, saved):
        # Only explicitly shaped nested views cross HTTP. Serialized raw records
        # contain complete PDF bytes and private authored expectations.
        excluded = {'execution', 'input_snapshot', 'memo', 'release', 'handoff', 'previous_failed_receipt', 'file', 'destination_copy'}
        result = {k: v for k, v in saved.items() if k not in excluded}
        result['record_sha256'] = encode(saved)[1]
        if kind == 'correction':
            result['input_snapshot'] = self.capture_view(GovernanceInputRepository.decode(saved['input_snapshot']))
        elif kind == 'finding':
            result['run'] = await self.run_view(GovernancePreparation.decode(saved['execution']))
        elif kind == 'memo':
            result['run'] = await self.run_view(GovernancePreparation.decode(saved['execution']))
            result['file'] = {k: v for k, v in saved['file'].items() if k != 'content_base64'}
        elif kind == 'release':
            result['memo'] = await self.record_view('memo', saved['memo'])
        elif kind == 'handoff':
            result['release'] = await self.record_view('release', saved['release'])
            result['destination_copy'] = {k: v for k, v in saved['destination_copy'].items() if k != 'content_base64'} if saved['destination_copy'] else None
            result['previous_failed_receipt'] = await self.record_view('handoff', saved['previous_failed_receipt']) if saved['previous_failed_receipt'] else None
        elif kind == 'review':
            result['handoff'] = await self.record_view('handoff', saved['handoff'])
        return result

    async def get(self, user_id, enrollment_id, reference, *, kind='review', delivery_enabled=False):
        enrollment, _, case = await self.course(user_id, enrollment_id)
        saved = await self.repositories()[kind].get(user_id, reference)
        if saved is None:
            raise GovernanceUnavailable('This saved capstone record is unavailable')
        self.verify(saved['plan'] if kind == 'run' else saved, enrollment, case)
        if kind == 'capture':
            return self.capture_view(saved)
        if kind == 'run':
            return await self.run_view(saved, writable=await self.writable(enrollment, delivery_enabled))
        return await self.record_view(kind, saved)

    async def list(self, user_id, enrollment_id, *, delivery_enabled=False):
        enrollment, _, case = await self.course(user_id, enrollment_id)
        query = {'user_id': user_id, 'enrollment_id': enrollment_id, 'module_id': 'governance'}
        result = {'enrollment_id': enrollment_id, 'module_id': 'governance', 'course_version': enrollment.course_version,
            'manifest_sha256': enrollment.manifest_sha256, 'case': case.public_definition(), 'records': {}}
        for kind, repository in self.repositories().items():
            selector = ({'record_kind': 'governance_extraction_input'} if kind == 'capture' else {} if kind == 'run' else
                {'prompt_id': {'scope': 'governance_execution_approval', 'correction': 'governance_scope_correction',
                    'finding': 'governance_original_source_finding', 'memo': 'governance_accountable_memo', 'release': 'governance_memo_release_choice',
                    'handoff': 'governance_private_training_handoff', 'review': 'governance_final_supervision_review'}[kind]})
            rows = await repository.records.find({**query, **selector}).sort('_id', -1).limit(51).to_list(51)
            summaries = []
            for raw in rows[:50]:
                saved = repository.decode(raw)
                record = saved['plan'] if kind == 'run' else saved
                self.verify(record, enrollment, case)
                summaries.append({'reference_id': record['uuid'], 'kind': kind,
                    'saved_at': record.get('captured_at', record.get('prepared_at', record.get('submitted_at'))),
                    'run_id': saved.get('run_id'), 'state': saved.get('state', saved.get('status')),
                    'phase': record.get('phase'), 'artifact_title': record.get('artifact', {}).get('title'),
                    'memo_id': record.get('submission', {}).get('memo_id'), 'previous_submission_id': record.get('submission', {}).get('previous_submission_id')})
            result['records'][kind] = {'items': summaries, 'older_available': len(rows) > 50}
        writable = await self.writable(enrollment, delivery_enabled)
        owned = await SearchSet.find({'user_id': user_id, 'set_type': 'extraction'}).sort('-updated_at').limit(51).to_list() if writable else []
        sources = []
        if writable:
            progress = await self.repository.read_progress(user_id, enrollment_id)
            for document_id in progress.modules.get('governance', {}).get('provisioned_docs', []):
                document = await owned_source(user_id, document_id, lab_folder_id=progress.lab_folder_id)
                if document:
                    sources.append({'document_id': document.uuid, 'title': document.title, 'text': document.raw_text,
                        'processing': document.processing, 'provenance': 'current_owned_workspace_ingestion'})
        return {**result, 'extractions': [{'artifact_id': item.uuid, 'title': item.title} for item in owned[:50]],
            'assigned_sources': sources, 'older_extractions_available': len(owned) > 50, 'can_submit': writable,
            'read_only_reason': None if writable else 'This is preserved course history. Select an available current course before saving new work.'}

    async def download(self, user_id, enrollment_id, reference, *, origin, source_id=None):
        enrollment, _, case = await self.course(user_id, enrollment_id)
        saved = await self.repositories()[origin].get(user_id, reference)
        if saved is None:
            raise GovernanceUnavailable('This preserved capstone file is unavailable')
        self.verify(saved['plan'] if origin == 'run' else saved, enrollment, case)
        if source_id is not None:
            if origin == 'capture':
                snapshot = saved
            elif origin == 'run':
                snapshot = saved['plan']['input_snapshot']
            elif origin == 'correction':
                snapshot = GovernanceInputRepository.decode(saved['input_snapshot'])
            elif origin == 'finding':
                snapshot = GovernancePreparation.decode(saved['execution'])['plan']['input_snapshot']
            elif origin in ('memo', 'release', 'handoff', 'review'):
                memo = saved if origin == 'memo' else saved['memo'] if origin == 'release' else saved['release']['memo'] if origin == 'handoff' else saved['handoff']['release']['memo']
                snapshot = GovernancePreparation.decode(memo['execution'])['plan']['input_snapshot']
            else:
                raise GovernanceUnavailable('This origin does not expose original source files')
            source = next((s for s in snapshot['documents'] if s['source_id'] == source_id), None)
            if source is None:
                raise GovernanceUnavailable('This file is not one of the complete original assigned records')
            return base64.b64decode(source['source_pdf_base64'], validate=True), source['assigned_filename'], 'application/pdf'
        file = (saved['file'] if origin == 'memo' else saved['memo']['file'] if origin == 'release' else (saved['destination_copy'] or saved['release']['memo']['file']) if origin == 'handoff'
            else saved['handoff']['destination_copy'] if origin == 'review' else None)
        if file is None:
            raise GovernanceUnavailable('This record has no confirmed saved memo copy')
        return base64.b64decode(file['content_base64'], validate=True), file['filename'], file['content_type']

    async def save(self, user_id, enrollment_id, payload, *, action):
        current = await self.repository.current(user_id)
        if current is None or current.uuid != enrollment_id:
            raise EnrollmentConflict('Select your existing course before saving or executing capstone work')
        _, package, _ = await self.course(user_id, enrollment_id)
        async with self.repository.write_boundary(user_id, enrollment_id, operation='governance_' + action) as progress:
            operation = CourseOperation(user_id, package, progress, True)
            if action == 'capture':
                return self.capture_view(await self.inputs.capture(operation, payload, actor_user_id=user_id, storage=get_storage()))
            if action in ('scope', 'correction', 'finding', 'memo', 'release', 'handoff', 'review'):
                saved = await self.repositories()[action].submit(operation, payload, actor_user_id=user_id)
                return await self.record_view(action, saved)
            if action == 'prepare':
                existing = await self.runs.records.find_one({'uuid': payload.request_id})
                config = {} if existing else await practical_preparation.configured_runtime()
                saved = await self.runs.prepare(operation, payload, config, actor_user_id=user_id)
            elif action == 'execute':
                existing = await self.runs.get(user_id, payload.run_id)
                config = await practical_preparation.configured_runtime() if existing and existing['state'] == 'prepared' else {}
                saved = await self.runs.execute(operation, payload, config, actor_user_id=user_id)
            elif action == 'finalize':
                saved = await GovernanceRecovery().finalize(operation, payload, actor_user_id=user_id)
            else:
                raise ValueError('Unsupported capstone action')
            return await self.run_view(saved, writable=True)


class GovernanceAssessment(ProcessAssessment):
    module_id = 'governance'
    channel = 'trusted_saved_governance_records'
    reference_key = 'governance_review_submission_id'
    assessment_kind = 'governance_capstone_review_draft'
    delivery_class = GovernanceDelivery
    prepare_method = 'prepare_from_governance_review'

    def __init__(self, repository=None):
        super().__init__(repository or EnrollmentRepository())
