"""Owned Batch learner actions and preserved source/run history."""
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
from .batch_approval import BatchScopeRepository
from .batch_case import load_batch_case
from .batch_execution import BatchExecution
from .batch_inputs import BatchInputRepository
from .batch_preparation import BatchPreparation
from .batch_recovery import BatchRecovery
from .batch_reviews import BatchReviewRepository, PROMPT_ID


class BatchUnavailable(ValueError):
    pass


class BatchDelivery:
    def __init__(self, repository=None):
        self.repository = repository or EnrollmentRepository()
        self.inputs = BatchInputRepository()
        self.runs = BatchExecution()
        self.scopes = BatchScopeRepository()
        self.reviews = BatchReviewRepository()

    async def course(self, user_id, enrollment_id):
        enrollment = await self.repository._enrollment(user_id, enrollment_id)
        package = self.repository.catalog.load(enrollment.course_version)
        if 'batch-cases/batch_processing.json' not in package.manifest.artifacts:
            raise BatchUnavailable('This course does not offer the bounded batch assessment')
        return enrollment, package, load_batch_case(package)

    @staticmethod
    def verify(record, enrollment, case):
        if (any(record[key] != value for key, value in {'user_id': enrollment.user_id,
                'enrollment_id': enrollment.uuid, 'course_version': enrollment.course_version,
                'manifest_sha256': enrollment.manifest_sha256, 'module_id': 'batch_processing'}.items())
                or record.get('case', record.get('input_snapshot', {}).get('case')) != case.public_definition()):
            raise CourseCatalogError('This saved batch work differs from its original course')

    async def writable(self, enrollment, enabled):
        selection = await self.repository.selections.find_one({'user_id': enrollment.user_id})
        return bool(enabled and enrollment.state in ('active', 'completed') and selection
                    and selection.get('active_enrollment_id') == enrollment.uuid)

    @staticmethod
    def capture_view(saved):
        return {key: saved[key] for key in ('uuid', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256',
            'case', 'artifact_id', 'artifact_sha256', 'artifact', 'captured_at')} | {
            'documents': [{key: value for key, value in source.items() if key != 'source_pdf_base64'} for source in saved['documents']],
            'input_snapshot_sha256': encode(saved)[1], 'execution_authorized': False, 'credit_awarded': False}

    async def run_view(self, run, *, writable=False):
        plan = run['plan']
        scope = run['authorization']['decision'] if run['authorization'] else None
        if scope is None and run['scope_decision_id']:
            scope = await self.scopes.get(plan['user_id'], run['scope_decision_id'])
        if scope is not None and (scope['run_id'] != run['run_id'] or scope['plan_sha256'] != run['plan_sha256']
                or scope['user_id'] != plan['user_id'] or scope['enrollment_id'] != plan['enrollment_id']
                or encode(scope)[1] != run['scope_decision_sha256']):
            raise CourseCatalogError('The displayed approval differs from this saved batch action')
        parent = BatchPreparation.decode(plan['parent_run_record']) if plan['parent_run_record'] else None
        previous = BatchPreparation.decode(plan['previous_retry_record']) if plan['previous_retry_record'] else None
        return {**{key: plan[key] for key in ('enrollment_id', 'module_id', 'course_version', 'manifest_sha256',
                    'input_snapshot_id', 'case_sha256', 'model_names', 'prepared_at', 'phase', 'batch_id', 'source_ids', 'failed_source_id')},
                **{key: run[key] for key in ('run_id', 'state', 'plan_sha256', 'scope_decision_id', 'scope_decision_sha256',
                                            'item_events', 'result')},
                'run_sha256': encode(run)[1],
                'input_snapshot': self.capture_view(plan['input_snapshot']), 'scope_decision': scope,
                'parent_run': await self.run_view(parent) if parent else None,
                'previous_retry': await self.run_view(previous) if previous else None,
                'authorization_sha256': encode(run['authorization'])[1] if run['authorization'] else None,
                'result_sha256': encode(run['result'])[1] if run['result'] else None,
                'item_events_sha256': encode(run['item_events'])[1],
                'can_save_scope': writable and run['state'] == 'prepared',
                'can_execute': bool(writable and run['state'] == 'prepared' and scope and scope['submission']['choice'] == 'approve'),
                'can_finalize': bool(writable and run['state'] == 'executing' and len(run['item_events']) == 2 * len(plan['item_plans'])),
                'credit_awarded': False, 'module_completion_eligible': False}

    def repositories(self):
        return {'capture': self.inputs, 'run': self.runs, 'scope': self.scopes, 'review': self.reviews}

    async def get(self, user_id, enrollment_id, reference, *, kind='review', delivery_enabled=False):
        enrollment, _, case = await self.course(user_id, enrollment_id)
        saved = await self.repositories()[kind].get(user_id, reference)
        if saved is None:
            raise BatchUnavailable('This saved batch record is unavailable')
        record = saved['plan'] if kind == 'run' else saved
        self.verify({**record, 'case': record.get('case', record.get('input_snapshot', {}).get('case', case.public_definition()))}, enrollment, case)
        if kind == 'scope':
            if saved['case_sha256'] != case.digest:
                raise CourseCatalogError('This choice belongs to a different batch assignment')
            return {**saved, 'decision_sha256': encode(saved)[1]}
        if kind == 'capture':
            return self.capture_view(saved)
        if kind == 'run':
            return await self.run_view(saved, writable=await self.writable(enrollment, delivery_enabled))
        return {key: saved[key] for key in ('uuid', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256',
            'case', 'submission', 'submitted_at', 'reconciliation', 'credit_awarded', 'module_completion_eligible')} | {
            'run': await self.run_view(BatchPreparation.decode(saved['execution'])),
            'retries': [await self.run_view(BatchPreparation.decode(raw)) for raw in saved['retry_executions']]}

    async def list(self, user_id, enrollment_id, *, delivery_enabled=False):
        enrollment, _, case = await self.course(user_id, enrollment_id)
        query = {'user_id': user_id, 'enrollment_id': enrollment_id, 'module_id': 'batch_processing'}
        result = {'enrollment_id': enrollment_id, 'module_id': 'batch_processing', 'course_version': enrollment.course_version,
                  'manifest_sha256': enrollment.manifest_sha256, 'case': case.public_definition()}
        for kind, repository, selector in (
                ('captures', self.inputs, {'record_kind': 'batch_extraction_input'}),
                ('runs', self.runs, {}),
                ('submissions', self.reviews, {'prompt_id': PROMPT_ID})):
            rows = await repository.records.find({**query, **selector}).sort('_id', -1).limit(51).to_list(51)
            summaries = []
            for raw in rows[:50]:
                saved = repository.decode(raw)
                record = saved['plan'] if kind == 'runs' else saved
                self.verify(record, enrollment, case)
                if kind == 'runs':
                    summaries.append({'run_id': saved['run_id'], 'state': saved['state'], 'phase': record['phase'],
                        'prepared_at': record['prepared_at'], 'input_snapshot_id': record['input_snapshot_id']})
                elif kind == 'captures':
                    summaries.append({'input_snapshot_id': record['uuid'], 'captured_at': record['captured_at'],
                                      'extraction_name': record['artifact']['title']})
                else:
                    summaries.append({'submission_id': record['uuid'], 'submitted_at': record['submitted_at'],
                        'run_id': record['run_id'], 'previous_submission_id': record['submission'].get('previous_submission_id')})
            result[kind] = summaries
            result['older_' + kind + '_available'] = len(rows) > 50
        writable = await self.writable(enrollment, delivery_enabled)
        owned = await SearchSet.find({'user_id': user_id, 'set_type': 'extraction'}).sort('-updated_at').limit(51).to_list() if writable else []
        sources = []
        if writable:
            progress = await self.repository.read_progress(user_id, enrollment_id)
            for document_id in progress.modules.get('batch_processing', {}).get('provisioned_docs', []):
                document = await owned_source(user_id, document_id, lab_folder_id=progress.lab_folder_id)
                if document:
                    sources.append({'document_id': document.uuid, 'title': document.title, 'text': document.raw_text,
                                    'processing': document.processing, 'provenance': 'current_owned_workspace_ingestion'})
        return {**result, 'extractions': [{'artifact_id': item.uuid, 'title': item.title} for item in owned[:50]],
                'assigned_sources': sources, 'older_extractions_available': len(owned) > 50, 'can_submit': writable,
                'read_only_reason': None if writable else 'This is preserved course history. Select an available current course before saving new work.'}

    async def download(self, user_id, enrollment_id, reference, *, origin, source_id):
        enrollment, _, case = await self.course(user_id, enrollment_id)
        saved = await self.repositories()[origin].get(user_id, reference)
        if saved is None:
            raise BatchUnavailable('This saved source is unavailable')
        record = saved['plan'] if origin == 'run' else saved
        self.verify(record, enrollment, case)
        if origin == 'capture':
            snapshot = saved
        elif origin == 'run':
            snapshot = saved['plan']['input_snapshot']
        else:
            snapshot = BatchPreparation.decode(saved['execution'])['plan']['input_snapshot']
        source = next((item for item in snapshot['documents'] if item['source_id'] == source_id), None)
        if source is None:
            raise BatchUnavailable('This source is not a member of the original assigned inventory')
        return base64.b64decode(source['source_pdf_base64'], validate=True), source['assigned_filename']

    async def save(self, user_id, enrollment_id, payload, *, action):
        current = await self.repository.current(user_id)
        if current is None or current.uuid != enrollment_id:
            raise EnrollmentConflict('Select your existing course before saving or executing batch work')
        _, package, _ = await self.course(user_id, enrollment_id)
        async with self.repository.write_boundary(user_id, enrollment_id, operation='batch_' + action) as progress:
            operation = CourseOperation(user_id, package, progress, True)
            if action == 'capture':
                return self.capture_view(await self.inputs.capture(operation, payload, actor_user_id=user_id, storage=get_storage()))
            if action == 'review':
                saved = await self.reviews.submit(operation, payload, actor_user_id=user_id)
                return await self.get(user_id, enrollment_id, saved['uuid'])
            if action == 'prepare':
                existing = await self.runs.records.find_one({'uuid': payload.request_id})
                config = {} if existing else await practical_preparation.configured_runtime()
                saved = await self.runs.prepare(operation, payload, config, actor_user_id=user_id)
            elif action == 'scope':
                await self.scopes.submit(operation, payload, actor_user_id=user_id)
                saved = await self.runs.get(user_id, payload.run_id)
            elif action == 'execute':
                existing = await self.runs.get(user_id, payload.run_id)
                config = await practical_preparation.configured_runtime() if existing and existing['state'] == 'prepared' else {}
                saved = await self.runs.execute(operation, payload, config, actor_user_id=user_id)
            elif action == 'finalize':
                saved = await BatchRecovery().finalize(operation, payload, actor_user_id=user_id)
            else:
                raise ValueError('Unsupported batch action')
            return await self.run_view(saved, writable=True)


class BatchAssessment(ProcessAssessment):
    module_id = 'batch_processing'
    channel = 'trusted_saved_batch_records'
    reference_key = 'batch_review_submission_id'
    assessment_kind = 'bounded_batch_review_draft'
    delivery_class = BatchDelivery
    prepare_method = 'prepare_from_batch_review'

    def __init__(self, repository=None):
        super().__init__(repository or EnrollmentRepository())
