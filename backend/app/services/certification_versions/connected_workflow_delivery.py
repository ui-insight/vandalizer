"""Authenticated learner delivery for explicit connected work and saved history."""
from app.models.workflow import Workflow
from app.services.storage import get_storage

from . import practical_preparation
from .attempts import encode
from .catalog import CourseCatalogError
from .connected_workflow_approval import ConnectedScopeRepository
from .connected_workflow_execution import ConnectedWorkflowExecution
from .connected_workflow_inputs import ConnectedWorkflowInputRepository
from .connected_workflow_recovery import ConnectedWorkflowRecovery
from .connected_workflow_reviews import ConnectedReviewRepository, PROMPT_ID
from .connected_recovery_decisions import ConnectedRecoveryDecisionRepository, PROMPT_ID as RECOVERY_PROMPT_ID
from .connected_failure_practice import is_failure_practice
from .enrollments import EnrollmentConflict, EnrollmentRepository
from .multi_step_case import load_multi_step_case
from .process_delivery import ProcessAssessment
from .runtime import CourseOperation


class ConnectedWorkflowUnavailable(ValueError):
    pass


class ConnectedWorkflowDelivery:
    def __init__(self, repository=None):
        self.repository = repository or EnrollmentRepository()
        self.inputs = ConnectedWorkflowInputRepository()
        self.runs = ConnectedWorkflowExecution()
        self.reviews = ConnectedReviewRepository()
        self.scopes = ConnectedScopeRepository()
        self.recovery_decisions = ConnectedRecoveryDecisionRepository()

    async def course(self, user_id, enrollment_id):
        enrollment = await self.repository._enrollment(user_id, enrollment_id)
        package = self.repository.catalog.load(enrollment.course_version)
        if 'connected-cases/multi_step.json' not in package.manifest.artifacts:
            raise ConnectedWorkflowUnavailable('This course does not offer the connected-workflow assessment')
        return enrollment, package, load_multi_step_case(package)

    @staticmethod
    def verify(record, enrollment, case):
        if (any(record[key] != value for key, value in {'user_id': enrollment.user_id,
                'enrollment_id': enrollment.uuid, 'course_version': enrollment.course_version,
                'manifest_sha256': enrollment.manifest_sha256, 'module_id': 'multi_step'}.items())
                or record.get('case', record.get('input_snapshot', {}).get('case')) != case.public_definition()):
            raise CourseCatalogError('This saved connected work does not match its original course')
        return record

    async def writable(self, enrollment, delivery_enabled):
        selection = await self.repository.selections.find_one({'user_id': enrollment.user_id})
        return bool(delivery_enabled and enrollment.state in ('active', 'completed')
                    and selection and selection.get('active_enrollment_id') == enrollment.uuid)

    @staticmethod
    def capture_view(snapshot):
        return {key: snapshot[key] for key in ('uuid', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256',
            'case', 'artifact_id', 'artifact_sha256', 'artifact', 'documents', 'captured_at')} | {
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
                **{key: run[key] for key in ('run_id', 'state', 'plan_sha256', 'scope_decision_id', 'scope_decision_sha256', 'stage_events', 'result')},
                'input_snapshot': self.capture_view(plan['input_snapshot']), 'scope_decision': scope,
                'execution_purpose': 'controlled_failure_rehearsal' if is_failure_practice(plan) else 'complete_internal_chain',
                'approval_question': plan['approval_requirement']['question'],
                'authorization_sha256': encode(run['authorization'])[1] if run['authorization'] else None,
                'result_sha256': encode(run['result'])[1] if run['result'] else None,
                'stage_events_sha256': encode(run['stage_events'])[1],
                'can_save_scope': writable and run['state'] == 'prepared',
                'can_execute': bool(writable and run['state'] == 'prepared' and scope and scope['submission']['choice'] == 'approve'),
                'can_finalize': writable and run['state'] == 'executing' and len(run['stage_events']) == 6
                    and all(item['receipt'].get('status') == 'completed' for item in run['stage_events'] if item['receipt']['kind'] == 'stage_completed'),
                'credit_awarded': False, 'module_completion_eligible': False}

    async def get(self, user_id, enrollment_id, reference, *, kind='review', delivery_enabled=False):
        enrollment, _, case = await self.course(user_id, enrollment_id)
        repository = {'capture': self.inputs, 'run': self.runs, 'review': self.reviews, 'scope': self.scopes,
                      'recovery': self.recovery_decisions}[kind]
        saved = await repository.get(user_id, reference)
        if saved is None:
            raise ConnectedWorkflowUnavailable('This saved connected-workflow record is unavailable')
        if kind == 'scope':
            if saved['case_sha256'] != case.digest:
                raise CourseCatalogError('This scope choice belongs to a different assignment')
            self.verify({**saved, 'case': case.public_definition()}, enrollment, case)
            return {**saved, 'decision_sha256': encode(saved)[1]}
        self.verify(saved['plan'] if kind == 'run' else saved, enrollment, case)
        if kind == 'capture':
            return self.capture_view(saved)
        if kind == 'run':
            return await self.run_view(saved, writable=await self.writable(enrollment, delivery_enabled))
        from .connected_workflow_preparation import ConnectedWorkflowPreparation
        if kind == 'recovery':
            return {key: saved[key] for key in ('uuid', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256',
                'case', 'submission', 'question', 'checks', 'submitted_at', 'credit_awarded', 'module_completion_eligible')} | {
                'stopped_run': await self.run_view(ConnectedWorkflowPreparation.decode(saved['stopped_execution']))}
        return {key: saved[key] for key in ('uuid', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256',
            'case', 'submission', 'comparison', 'submitted_at', 'credit_awarded', 'module_completion_eligible')} | {
            name + '_run': await self.run_view(ConnectedWorkflowPreparation.decode(saved[name + '_execution']))
            for name in ('original', 'corrected')}

    async def list(self, user_id, enrollment_id, *, delivery_enabled=False):
        enrollment, _, case = await self.course(user_id, enrollment_id)
        query = {'user_id': user_id, 'enrollment_id': enrollment_id, 'module_id': 'multi_step'}
        result = {'enrollment_id': enrollment_id, 'module_id': 'multi_step', 'course_version': enrollment.course_version,
                  'manifest_sha256': enrollment.manifest_sha256, 'case': case.public_definition()}
        for kind, repository in (('captures', self.inputs), ('runs', self.runs), ('submissions', self.reviews), ('recovery_submissions', self.recovery_decisions)):
            prompt_filter = {'prompt_id': PROMPT_ID if kind == 'submissions' else RECOVERY_PROMPT_ID} if kind.endswith('submissions') else {}
            rows = await repository.records.find({**query, **prompt_filter}).sort('_id', -1).limit(51).to_list(51)
            summaries = []
            for raw in rows[:50]:
                saved = repository.decode(raw)
                record = saved['plan'] if kind == 'runs' else saved
                self.verify(record, enrollment, case)
                if kind == 'runs':
                    summaries.append({'run_id': saved['run_id'], 'state': saved['state'], 'prepared_at': record['prepared_at'],
                        'input_snapshot_id': record['input_snapshot_id'], 'workflow_name': record['input_snapshot']['artifact']['workflow']['name']})
                elif kind == 'captures':
                    summaries.append({'input_snapshot_id': record['uuid'], 'captured_at': record['captured_at'],
                                      'workflow_name': record['artifact']['workflow']['name']})
                elif kind == 'recovery_submissions':
                    summaries.append({'submission_id': record['uuid'], 'submitted_at': record['submitted_at'],
                        'run_id': record['run_id'], 'previous_submission_id': record['submission']['previous_submission_id'],
                        'choices_supported': record['checks']['choices_supported']})
                else:
                    summaries.append({'submission_id': record['uuid'], 'submitted_at': record['submitted_at'],
                        **{key: record['submission'][key] for key in ('previous_submission_id', 'original_run_id', 'corrected_run_id')}})
            result[kind] = summaries
            result['older_' + kind + '_available'] = len(rows) > 50
        writable = await self.writable(enrollment, delivery_enabled)
        owned = await Workflow.find({'user_id': user_id}).sort('-updated_at').limit(51).to_list() if writable else []
        return {**result, 'workflows': [{'workflow_id': str(item.id), 'name': item.name, 'version': item.version} for item in owned[:50]],
                'older_workflows_available': len(owned) > 50, 'can_submit': writable,
                'read_only_reason': None if writable else 'This is preserved course history. Select an available current course before saving new work.'}

    async def save(self, user_id, enrollment_id, payload, *, action):
        current = await self.repository.current(user_id)
        if current is None or current.uuid != enrollment_id:
            raise EnrollmentConflict('Select your existing course before saving or executing connected work')
        _, package, _ = await self.course(user_id, enrollment_id)
        async with self.repository.write_boundary(user_id, enrollment_id, operation='connected_' + action) as progress:
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
                saved = await ConnectedWorkflowRecovery().finalize(operation, payload, actor_user_id=user_id)
            elif action == 'review':
                saved = await self.reviews.submit(operation, payload, actor_user_id=user_id)
                return await self.get(user_id, enrollment_id, saved['uuid'])
            elif action == 'recovery':
                saved = await self.recovery_decisions.submit(operation, payload, actor_user_id=user_id)
                return await self.get(user_id, enrollment_id, saved['uuid'], kind='recovery')
            else:
                raise ValueError('Unsupported connected action')
            return await self.run_view(saved, writable=True)


class ConnectedWorkflowAssessment(ProcessAssessment):
    module_id = 'multi_step'
    channel = 'trusted_saved_connected_records'
    reference_key = 'connected_review_submission_id'
    assessment_kind = 'connected_workflow_review_draft'
    delivery_class = ConnectedWorkflowDelivery
    prepare_method = 'prepare_from_connected_review'

    def __init__(self, repository=None):
        super().__init__(repository or EnrollmentRepository())
