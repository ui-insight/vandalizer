"""Authenticated learner delivery for explicit output work and saved history."""
from app.models.workflow import Workflow
from .source_access import owned_source
from app.services.storage import get_storage

from . import practical_preparation
from .attempts import encode
from .catalog import CourseCatalogError
from .output_workflow_approval import OutputScopeRepository
from .output_workflow_execution import OutputWorkflowExecution
from .output_workflow_preparation import OutputWorkflowPreparation
from .output_workflow_inputs import OutputWorkflowInputRepository
from .output_workflow_recovery import OutputWorkflowRecovery
from .output_outcome_reviews import OutputOutcomeReviewRepository, PROMPT_ID, restore_handoff
from .output_file_reviews import OutputFileReviewRepository, PROMPT_ID as FILE_PROMPT
from .output_private_handoff import OutputPrivateHandoffRepository, PROMPT_ID as HANDOFF_PROMPT
from .enrollments import EnrollmentConflict, EnrollmentRepository
from .output_case import load_output_case
from .process_delivery import ProcessAssessment
from .runtime import CourseOperation


class OutputWorkflowUnavailable(ValueError):
    pass


class OutputWorkflowDelivery:
    def __init__(self, repository=None):
        self.repository = repository or EnrollmentRepository()
        self.inputs = OutputWorkflowInputRepository()
        self.runs = OutputWorkflowExecution()
        self.reviews = OutputOutcomeReviewRepository()
        self.file_reviews = OutputFileReviewRepository()
        self.handoffs = OutputPrivateHandoffRepository()
        self.scopes = OutputScopeRepository()

    async def course(self, user_id, enrollment_id):
        enrollment = await self.repository._enrollment(user_id, enrollment_id)
        package = self.repository.catalog.load(enrollment.course_version)
        if 'output-cases/output_delivery.json' not in package.manifest.artifacts:
            raise OutputWorkflowUnavailable('This course does not offer the output workflow assessment')
        return enrollment, package, load_output_case(package)

    @staticmethod
    def verify(record, enrollment, case):
        if (any(record[key] != value for key, value in {'user_id': enrollment.user_id,
                'enrollment_id': enrollment.uuid, 'course_version': enrollment.course_version,
                'manifest_sha256': enrollment.manifest_sha256, 'module_id': 'output_delivery'}.items())
                or record.get('case', record.get('input_snapshot', {}).get('case')) != case.public_definition()):
            raise CourseCatalogError('This saved output work does not match its original course')
        return record

    async def writable(self, enrollment, delivery_enabled):
        selection = await self.repository.selections.find_one({'user_id': enrollment.user_id})
        return bool(delivery_enabled and enrollment.state in ('active', 'completed')
                    and selection and selection.get('active_enrollment_id') == enrollment.uuid)

    @staticmethod
    def capture_view(snapshot):
        return {key: snapshot[key] for key in ('uuid', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256',
            'case', 'artifact_id', 'artifact_sha256', 'artifact', 'captured_at')} | {
            'documents': [{key: value for key, value in document.items() if key != 'source_pdf_base64'} for document in snapshot['documents']],
            'input_snapshot_sha256': encode(snapshot)[1], 'execution_authorized': False, 'credit_awarded': False}

    @staticmethod
    def artifacts_view(artifacts):
        return {**artifacts, 'files': [{key: value for key, value in file.items() if key != 'data_base64'} for file in artifacts['files']],
            'download': {key: value for key, value in artifacts['download'].items() if key != 'data_base64'},
            'artifacts_sha256': encode(artifacts)[1]}

    @staticmethod
    def stage_view(events):
        # Display actual text/file metadata without duplicating binary payloads.
        def strip(value):
            if isinstance(value, dict):
                return {key: strip(item) for key, item in value.items() if key != 'data_b64'}
            if isinstance(value, list):
                return [strip(item) for item in value]
            return value
        return strip(events)

    def handoff_view(self, saved):
        return {key: value for key, value in saved.items() if key not in ('destination_copy', 'release_authorization', 'previous_failed_receipt')} | {
            'handoff_sha256': encode(saved)[1],
            'destination_copy': self.artifacts_view(saved['destination_copy']) if saved['destination_copy'] else None,
            'previous_failed_receipt': self.handoff_view(saved['previous_failed_receipt']) if saved['previous_failed_receipt'] else None}

    async def file_review_view(self, saved):
        return {key: saved[key] for key in ('uuid', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256',
            'case', 'submission', 'submitted_at', 'previous_release_decision_id', 'credit_awarded', 'module_completion_eligible')} | {
            'review_sha256': encode(saved)[1], 'run': await self.run_view(OutputWorkflowPreparation.decode(saved['execution']))}

    async def run_view(self, run, *, writable=False):
        plan = run['plan']
        scope = run['authorization']['decision'] if run['authorization'] else None
        if scope is None and run['scope_decision_id']:
            scope = await self.scopes.get(plan['user_id'], run['scope_decision_id'])
        if scope is not None and (scope['run_id'] != run['run_id'] or scope['plan_sha256'] != run['plan_sha256']
                or scope['user_id'] != plan['user_id'] or scope['enrollment_id'] != plan['enrollment_id']
                or encode(scope)[1] != run['scope_decision_sha256']):
            raise CourseCatalogError('The displayed scope choice differs from this saved run')
        raw = await self.runs.records.find_one({'uuid': run['run_id'], 'user_id': plan['user_id']})
        release = await self.file_reviews.get(plan['user_id'], raw.get('release_decision_id')) if raw else None
        if release and (release['run_id'] != run['run_id'] or encode(release)[1] != raw.get('release_decision_sha256')
                or release['submission']['result_sha256'] != encode(run['result'])[1]):
            raise CourseCatalogError('The linked release choice does not match the generated files')
        result = run['result']
        if result and result.get('generated_artifacts'):
            result = {**result, 'generated_artifacts': self.artifacts_view(result['generated_artifacts'])}
        return {**{key: plan[key] for key in ('enrollment_id', 'module_id', 'course_version', 'manifest_sha256',
                    'input_snapshot_id', 'case_sha256', 'model_names', 'stage_plans', 'prepared_at')},
                **{key: run[key] for key in ('run_id', 'state', 'plan_sha256', 'scope_decision_id', 'scope_decision_sha256')},
                'stage_events': self.stage_view(run['stage_events']), 'result': result,
                'input_snapshot': self.capture_view(plan['input_snapshot']), 'scope_decision': scope,
                'authorization_sha256': encode(run['authorization'])[1] if run['authorization'] else None,
                'result_sha256': encode(run['result'])[1] if run['result'] else None,
                'stage_events_sha256': encode(run['stage_events'])[1],
                'can_save_scope': writable and run['state'] == 'prepared',
                'can_execute': bool(writable and run['state'] == 'prepared' and scope and scope['submission']['choice'] == 'approve'),
                'can_finalize': writable and run['state'] == 'executing'
                    and len(run['stage_events']) == 8
                    and not any(item['receipt'].get('status') == 'failed' for item in run['stage_events']),
                'release_decision': ({'uuid': release['uuid'], 'review_sha256': encode(release)[1], 'submission': release['submission']} if release else None),
                'handoff_request_id': raw.get('output_handoff_request_id') if raw else None,
                'retry_request_id': raw.get('output_retry_request_id') if raw else None,
                'handoff_receipt_id': raw.get('output_handoff_receipt_id') if raw else None,
                'handoff_claimed': bool(raw and raw.get('output_handoff_claimed')),
                'can_inspect': bool(writable and run['state'] == 'completed' and raw and not raw.get('output_handoff_claimed')),
                'credit_awarded': False, 'module_completion_eligible': False}

    async def get(self, user_id, enrollment_id, reference, *, kind='review', delivery_enabled=False):
        enrollment, _, case = await self.course(user_id, enrollment_id)
        repository = {'capture': self.inputs, 'run': self.runs, 'review': self.reviews, 'scope': self.scopes, 'inspection': self.file_reviews, 'handoff': self.handoffs}[kind]
        saved = await repository.get(user_id, reference)
        if saved is None:
            raise OutputWorkflowUnavailable('This saved output workflow record is unavailable')
        if kind == 'scope':
            if saved['case_sha256'] != case.digest:
                raise CourseCatalogError('This scope choice belongs to a different assignment')
            self.verify({**saved, 'case': case.public_definition()}, enrollment, case)
            return {**saved, 'decision_sha256': encode(saved)[1]}
        self.verify(saved['plan'] if kind == 'run' else {**saved, 'case': saved.get('case', case.public_definition())}, enrollment, case)
        if kind == 'capture':
            return self.capture_view(saved)
        if kind == 'run':
            return await self.run_view(saved, writable=await self.writable(enrollment, delivery_enabled))
        if kind == 'inspection':
            return await self.file_review_view(saved)
        if kind == 'handoff':
            return self.handoff_view(saved)
        review = OutputFileReviewRepository.decode(saved['file_review'])
        run = OutputWorkflowPreparation.decode(review['execution'])
        return {key: saved[key] for key in ('uuid', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256',
            'case', 'submission', 'submitted_at', 'credit_awarded', 'module_completion_eligible')} | {
            'file_review': await self.file_review_view(review),
            'handoff': self.handoff_view(restore_handoff(saved['handoff'], run['result']['generated_artifacts']))}

    async def list(self, user_id, enrollment_id, *, delivery_enabled=False):
        enrollment, _, case = await self.course(user_id, enrollment_id)
        query = {'user_id': user_id, 'enrollment_id': enrollment_id, 'module_id': 'output_delivery'}
        result = {'enrollment_id': enrollment_id, 'module_id': 'output_delivery', 'course_version': enrollment.course_version,
                  'manifest_sha256': enrollment.manifest_sha256, 'case': case.public_definition()}
        for kind, repository in (('captures', self.inputs), ('runs', self.runs), ('inspections', self.file_reviews),
                                 ('handoffs', self.handoffs), ('submissions', self.reviews)):
            selector = ({'record_kind': 'output_workflow_input'} if kind == 'captures'
                        else {'prompt_id': {'inspections': FILE_PROMPT, 'handoffs': HANDOFF_PROMPT, 'submissions': PROMPT_ID}[kind]}
                        if kind in ('inspections', 'handoffs', 'submissions') else {})
            rows = await repository.records.find({**query, **selector}).sort('_id', -1).limit(51).to_list(51)
            summaries = []
            for raw in rows[:50]:
                saved = repository.decode(raw)
                record = saved['plan'] if kind == 'runs' else saved
                self.verify({**record, 'case': record.get('case', record.get('input_snapshot', {}).get('case', case.public_definition()))}, enrollment, case)
                if kind == 'runs':
                    summaries.append({'run_id': saved['run_id'], 'state': saved['state'], 'prepared_at': record['prepared_at'],
                        'input_snapshot_id': record['input_snapshot_id'], 'workflow_name': record['input_snapshot']['artifact']['workflow']['name']})
                elif kind == 'captures':
                    summaries.append({'input_snapshot_id': record['uuid'], 'captured_at': record['captured_at'],
                                      'workflow_name': record['artifact']['workflow']['name']})
                else:
                    summaries.append({'submission_id': record['uuid'], 'submitted_at': record['submitted_at'],
                        'run_id': record['run_id'], 'status': record.get('status'), 'choice': record['submission'].get('choice'),
                        'previous_submission_id': record['submission'].get('previous_submission_id')})
            result[kind] = summaries
            result['older_' + kind + '_available'] = len(rows) > 50
        writable = await self.writable(enrollment, delivery_enabled)
        owned = await Workflow.find({'user_id': user_id}).sort('-updated_at').limit(51).to_list() if writable else []
        sources = []
        if writable:
            progress = await self.repository.read_progress(user_id, enrollment_id)
            for document_id in progress.modules.get('output_delivery', {}).get('provisioned_docs', []):
                document = await owned_source(user_id, document_id, lab_folder_id=progress.lab_folder_id)
                if document:
                    sources.append({'document_id': document.uuid, 'title': document.title, 'text': document.raw_text,
                                    'processing': document.processing, 'provenance': 'current_owned_workspace_ingestion'})
        return {**result, 'workflows': [{'workflow_id': str(item.id), 'name': item.name, 'version': item.version} for item in owned[:50]],
                'assigned_sources': sources,
                'older_workflows_available': len(owned) > 50, 'can_submit': writable,
                'read_only_reason': None if writable else 'This is preserved course history. Select an available current course before saving new work.'}

    async def download(self, user_id, enrollment_id, reference, *, origin, kind, file_index=0):
        import base64
        from .output_artifacts import MEDIA_TYPES
        enrollment, _, case = await self.course(user_id, enrollment_id)
        repository = {'run': self.runs, 'inspection': self.file_reviews, 'review': self.reviews, 'handoff': self.handoffs}[origin]
        saved = await repository.get(user_id, reference)
        if saved is None:
            raise OutputWorkflowUnavailable('This saved file is unavailable')
        if origin == 'run':
            run = saved
        elif origin == 'inspection':
            run = OutputWorkflowPreparation.decode(saved['execution'])
        elif origin == 'review':
            review = OutputFileReviewRepository.decode(saved['file_review'])
            run = OutputWorkflowPreparation.decode(review['execution'])
        else:
            self.verify({**saved, 'case': case.public_definition()}, enrollment, case)
            if kind == 'source' or saved['destination_copy'] is None:
                raise OutputWorkflowUnavailable('This handoff has no saved private file copy')
            run = None
        if run is not None:
            self.verify(run['plan'], enrollment, case)
            if kind == 'source':
                document = run['plan']['input_snapshot']['documents'][0]
                return base64.b64decode(document['source_pdf_base64'], validate=True), 'application/pdf', case.source_filename
            if run['state'] != 'completed':
                raise OutputWorkflowUnavailable('This run has no completed generated files')
            artifacts = run['result']['generated_artifacts']
        else:
            artifacts = saved['destination_copy']
        if kind == 'bundle':
            item = artifacts['download']
        else:
            if file_index < 0 or file_index >= len(artifacts['files']):
                raise OutputWorkflowUnavailable('This file is not a member of the saved bundle')
            item = artifacts['files'][file_index]
        return (base64.b64decode(item['data_base64'], validate=True),
                item.get('media_type') or MEDIA_TYPES.get(item['file_type'], 'application/octet-stream'), item['filename'])

    async def save(self, user_id, enrollment_id, payload, *, action):
        current = await self.repository.current(user_id)
        if current is None or current.uuid != enrollment_id:
            raise EnrollmentConflict('Select your existing course before saving or executing output work')
        _, package, _ = await self.course(user_id, enrollment_id)
        async with self.repository.write_boundary(user_id, enrollment_id, operation='output_' + action) as progress:
            operation = CourseOperation(user_id, package, progress, True)
            if action == 'capture':
                saved = await self.inputs.capture(operation, payload, actor_user_id=user_id, storage=get_storage())
                return self.capture_view(saved)
            if action == 'prepare':
                # Replaying a prepared receipt must not depend on live settings.
                existing = await self.runs.records.find_one({'uuid': payload.request_id})
                config = {} if existing else await practical_preparation.configured_runtime()
                models = config.get('available_models') or []
                default = config.get('default_model') or (models[0].get('name') if models else '')
                saved = await self.runs.prepare(operation, payload, config, actor_user_id=user_id, default_model=default)
            elif action == 'scope':
                await self.scopes.submit(operation, payload, actor_user_id=user_id)
                saved = await self.runs.get(user_id, payload.run_id)
            elif action == 'execute':
                existing = await self.runs.get(user_id, payload.run_id)
                config = await practical_preparation.configured_runtime() if existing and existing['state'] == 'prepared' else {}
                saved = await self.runs.execute(operation, payload, config, actor_user_id=user_id)
            elif action == 'finalize':
                saved = await OutputWorkflowRecovery().finalize(operation, payload, actor_user_id=user_id)
            elif action == 'inspection':
                saved = await self.file_reviews.submit(operation, payload, actor_user_id=user_id)
                return await self.file_review_view(saved)
            elif action == 'handoff':
                saved = await self.handoffs.submit(operation, payload, actor_user_id=user_id)
                return self.handoff_view(saved)
            elif action == 'review':
                saved = await self.reviews.submit(operation, payload, actor_user_id=user_id)
                return await self.get(user_id, enrollment_id, saved['uuid'])
            else:
                raise ValueError('Unsupported output action')
            return await self.run_view(saved, writable=True)


class OutputWorkflowAssessment(ProcessAssessment):
    module_id = 'output_delivery'
    channel = 'trusted_saved_output_records'
    reference_key = 'output_review_submission_id'
    assessment_kind = 'output_workflow_review_draft'
    delivery_class = OutputWorkflowDelivery
    prepare_method = 'prepare_from_output_review'

    def __init__(self, repository=None):
        super().__init__(repository or EnrollmentRepository())
