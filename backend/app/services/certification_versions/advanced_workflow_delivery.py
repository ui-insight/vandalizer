"""Authenticated learner delivery for explicit budget work and saved history."""
from app.models.workflow import Workflow
from .source_access import owned_source
from app.services.storage import get_storage

from . import practical_preparation
from .attempts import encode
from .advanced_calculation_records import AdvancedCalculationRepository
from .catalog import CourseCatalogError
from .advanced_workflow_approval import AdvancedScopeRepository
from .advanced_workflow_execution import AdvancedWorkflowExecution
from .advanced_workflow_inputs import AdvancedWorkflowInputRepository
from .advanced_workflow_recovery import AdvancedWorkflowRecovery
from .advanced_workflow_reviews import AdvancedReviewRepository, PROMPT_ID
from .enrollments import EnrollmentConflict, EnrollmentRepository
from .advanced_case import load_advanced_case
from .process_delivery import ProcessAssessment
from .runtime import CourseOperation


class AdvancedWorkflowUnavailable(ValueError):
    pass


class AdvancedWorkflowDelivery:
    def __init__(self, repository=None):
        self.repository = repository or EnrollmentRepository()
        self.inputs = AdvancedWorkflowInputRepository()
        self.calculations = AdvancedCalculationRepository()
        self.runs = AdvancedWorkflowExecution()
        self.reviews = AdvancedReviewRepository()
        self.scopes = AdvancedScopeRepository()

    async def course(self, user_id, enrollment_id):
        enrollment = await self.repository._enrollment(user_id, enrollment_id)
        package = self.repository.catalog.load(enrollment.course_version)
        if 'advanced-cases/advanced_nodes.json' not in package.manifest.artifacts:
            raise AdvancedWorkflowUnavailable('This course does not offer the budget workflow assessment')
        return enrollment, package, load_advanced_case(package)

    @staticmethod
    def verify(record, enrollment, case):
        if (any(record[key] != value for key, value in {'user_id': enrollment.user_id,
                'enrollment_id': enrollment.uuid, 'course_version': enrollment.course_version,
                'manifest_sha256': enrollment.manifest_sha256, 'module_id': 'advanced_nodes'}.items())
                or record.get('case', record.get('input_snapshot', {}).get('case')) != case.public_definition()):
            raise CourseCatalogError('This saved budget work does not match its original course')
        return record

    async def writable(self, enrollment, delivery_enabled):
        selection = await self.repository.selections.find_one({'user_id': enrollment.user_id})
        return bool(delivery_enabled and enrollment.state in ('active', 'completed')
                    and selection and selection.get('active_enrollment_id') == enrollment.uuid)

    @staticmethod
    def calculation_view(snapshot):
        return {key: snapshot[key] for key in ('uuid', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256',
            'case', 'request', 'document', 'checks', 'captured_at', 'credit_awarded', 'module_completion_eligible')} | {
            'calculation_snapshot_sha256': encode(snapshot)[1]}

    @staticmethod
    def capture_view(snapshot):
        return {key: snapshot[key] for key in ('uuid', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256',
            'case', 'artifact_id', 'artifact_sha256', 'artifact', 'captured_at')} | {
            'calculation': AdvancedWorkflowDelivery.calculation_view(snapshot['calculation_snapshot']),
            'method_choice': snapshot['request']['method_choice'],
            'input_snapshot_sha256': encode(snapshot)[1], 'execution_authorized': False, 'credit_awarded': False}

    async def run_view(self, run, *, writable=False):
        plan = run['plan']
        scope = run['authorization']['decision'] if run['authorization'] else None
        if scope is None and run['scope_decision_id']:
            scope = await self.scopes.get(plan['user_id'], run['scope_decision_id'])
        if scope is not None and (scope['run_id'] != run['run_id'] or scope['plan_sha256'] != run['plan_sha256']
                or scope['user_id'] != plan['user_id'] or scope['enrollment_id'] != plan['enrollment_id']
                or encode(scope)[1] != run['scope_decision_sha256']):
            raise CourseCatalogError('The displayed scope choice differs from this saved run')
        return {**{key: plan[key] for key in ('enrollment_id', 'module_id', 'course_version', 'manifest_sha256',
                    'input_snapshot_id', 'case_sha256', 'model_names', 'stage_plans', 'prepared_at')},
                **{key: run[key] for key in ('run_id', 'state', 'plan_sha256', 'scope_decision_id', 'scope_decision_sha256', 'task_events', 'result')},
                'input_snapshot': self.capture_view(plan['input_snapshot']), 'scope_decision': scope,
                'authorization_sha256': encode(run['authorization'])[1] if run['authorization'] else None,
                'result_sha256': encode(run['result'])[1] if run['result'] else None,
                'task_events_sha256': encode(run['task_events'])[1],
                'can_save_scope': writable and run['state'] == 'prepared',
                'can_execute': bool(writable and run['state'] == 'prepared' and scope and scope['submission']['choice'] == 'approve'),
                'can_finalize': writable and run['state'] == 'executing'
                    and len(run['task_events']) == 2 * sum(len(stage['tasks']) for stage in plan['stage_plans'])
                    and not any(item['receipt']['kind'] == 'task_failed' for item in run['task_events']),
                'credit_awarded': False, 'module_completion_eligible': False}

    async def get(self, user_id, enrollment_id, reference, *, kind='review', delivery_enabled=False):
        enrollment, _, case = await self.course(user_id, enrollment_id)
        repository = {'calculation': self.calculations, 'capture': self.inputs, 'run': self.runs, 'review': self.reviews, 'scope': self.scopes}[kind]
        saved = await repository.get(user_id, reference)
        if saved is None:
            raise AdvancedWorkflowUnavailable('This saved budget workflow record is unavailable')
        if kind == 'scope':
            if saved['case_sha256'] != case.digest:
                raise CourseCatalogError('This scope choice belongs to a different assignment')
            self.verify({**saved, 'case': case.public_definition()}, enrollment, case)
            return {**saved, 'decision_sha256': encode(saved)[1]}
        self.verify(saved['plan'] if kind == 'run' else saved, enrollment, case)
        if kind == 'calculation':
            return self.calculation_view(saved)
        if kind == 'capture':
            return self.capture_view(saved)
        if kind == 'run':
            return await self.run_view(saved, writable=await self.writable(enrollment, delivery_enabled))
        from .advanced_workflow_preparation import AdvancedWorkflowPreparation
        return {key: saved[key] for key in ('uuid', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256',
            'case', 'submission', 'submitted_at', 'credit_awarded', 'module_completion_eligible')} | {
            'run': await self.run_view(AdvancedWorkflowPreparation.decode(saved['execution']))}

    async def list(self, user_id, enrollment_id, *, delivery_enabled=False):
        enrollment, _, case = await self.course(user_id, enrollment_id)
        query = {'user_id': user_id, 'enrollment_id': enrollment_id, 'module_id': 'advanced_nodes'}
        result = {'enrollment_id': enrollment_id, 'module_id': 'advanced_nodes', 'course_version': enrollment.course_version,
                  'manifest_sha256': enrollment.manifest_sha256, 'case': case.public_definition(),
                  'calculation_fields': [{'id': check.id, 'unit': check.unit, 'operation': check.operation,
                      'inputs': [{'id': amount.id, 'label': amount.label, 'source_page': amount.anchor.page}
                                 for name in check.inputs for amount in case.amounts if amount.id == name]}
                      for check in case.calculations]}
        for kind, repository in (('calculations', self.calculations), ('captures', self.inputs), ('runs', self.runs), ('submissions', self.reviews)):
            selector = ({'record_kind': 'advanced_calculation_input'} if kind == 'calculations'
                        else {'record_kind': 'advanced_workflow_input'} if kind == 'captures'
                        else {'prompt_id': PROMPT_ID} if kind == 'submissions' else {})
            rows = await repository.records.find({**query, **selector}).sort('_id', -1).limit(51).to_list(51)
            summaries = []
            for raw in rows[:50]:
                saved = repository.decode(raw)
                record = saved['plan'] if kind == 'runs' else saved
                self.verify(record, enrollment, case)
                if kind == 'runs':
                    summaries.append({'run_id': saved['run_id'], 'state': saved['state'], 'prepared_at': record['prepared_at'],
                        'input_snapshot_id': record['input_snapshot_id'], 'workflow_name': record['input_snapshot']['artifact']['workflow']['name']})
                elif kind == 'calculations':
                    summaries.append({'calculation_snapshot_id': record['uuid'], 'captured_at': record['captured_at'],
                        'calculation_snapshot_sha256': encode(record)[1],
                        'all_arithmetic_supported': record['checks']['all_arithmetic_supported'],
                        'previous_snapshot_id': record['request']['previous_snapshot_id']})
                elif kind == 'captures':
                    summaries.append({'input_snapshot_id': record['uuid'], 'captured_at': record['captured_at'],
                                      'workflow_name': record['artifact']['workflow']['name']})
                else:
                    summaries.append({'submission_id': record['uuid'], 'submitted_at': record['submitted_at'],
                        **{key: record['submission'][key] for key in ('previous_submission_id', 'run_id')}})
            result[kind] = summaries
            result['older_' + kind + '_available'] = len(rows) > 50
        writable = await self.writable(enrollment, delivery_enabled)
        owned = await Workflow.find({'user_id': user_id}).sort('-updated_at').limit(51).to_list() if writable else []
        sources = []
        if writable:
            progress = await self.repository.read_progress(user_id, enrollment_id)
            for document_id in progress.modules.get('advanced_nodes', {}).get('provisioned_docs', []):
                document = await owned_source(user_id, document_id, lab_folder_id=progress.lab_folder_id)
                if document:
                    sources.append({'document_id': document.uuid, 'title': document.title, 'text': document.raw_text,
                                    'processing': document.processing, 'provenance': 'current_owned_workspace_ingestion'})
        return {**result, 'workflows': [{'workflow_id': str(item.id), 'name': item.name, 'version': item.version} for item in owned[:50]],
                'assigned_sources': sources,
                'older_workflows_available': len(owned) > 50, 'can_submit': writable,
                'read_only_reason': None if writable else 'This is preserved course history. Select an available current course before saving new work.'}

    async def save(self, user_id, enrollment_id, payload, *, action):
        current = await self.repository.current(user_id)
        if current is None or current.uuid != enrollment_id:
            raise EnrollmentConflict('Select your existing course before saving or executing budget work')
        _, package, _ = await self.course(user_id, enrollment_id)
        async with self.repository.write_boundary(user_id, enrollment_id, operation='budget_' + action) as progress:
            operation = CourseOperation(user_id, package, progress, True)
            if action == 'calculation':
                saved = await self.calculations.submit(operation, payload, actor_user_id=user_id, storage=get_storage())
                return self.calculation_view(saved)
            if action == 'capture':
                saved = await self.inputs.capture(operation, payload, actor_user_id=user_id)
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
                saved = await AdvancedWorkflowRecovery().finalize(operation, payload, actor_user_id=user_id)
            elif action == 'review':
                saved = await self.reviews.submit(operation, payload, actor_user_id=user_id)
                return await self.get(user_id, enrollment_id, saved['uuid'])
            else:
                raise ValueError('Unsupported budget action')
            return await self.run_view(saved, writable=True)


class AdvancedWorkflowAssessment(ProcessAssessment):
    module_id = 'advanced_nodes'
    channel = 'trusted_saved_budget_records'
    reference_key = 'budget_review_submission_id'
    assessment_kind = 'budget_workflow_review_draft'
    delivery_class = AdvancedWorkflowDelivery
    prepare_method = 'prepare_from_budget_review'

    def __init__(self, repository=None):
        super().__init__(repository or EnrollmentRepository())
