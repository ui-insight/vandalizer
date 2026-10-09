"""Course reads and saved position are resolved through an explicit enrollment.

This explicit-enrollment library supports the disabled-by-default rollout.
Chat/API request pinning lives in runtime; server position UI wiring is separate.
"""
import datetime
import hashlib

from app.models.certification import CertificationProgress
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict, EnrollmentRepository
from .grading import grade, selected_outcome_completion_available
from .writes import progress_filter


def public_modules(package):
    """Deliver pinned teaching and recognition prompts without answer keys."""
    from .scenario_submissions import module_bank
    lessons = package.json('lessons.json')
    modules = []
    for module in package.json('panel-modules.json'):
        item = {**module, 'assessment': lessons[module['id']].get('assessment')}
        if f"assessments/{module['id']}.json" in package.manifest.artifacts:
            item['scenarioAssessment'] = module_bank(package, module['id']).public_definition()
            item['assessment'] = None
        if f"process-cases/{module['id']}.json" in package.manifest.artifacts:
            from .process_case import load_process_case
            item['processAssessment'] = load_process_case(package, module['id']).public_definition()
            item['assessment'] = None
        decision_path = f"decisions/{module['id']}.json"
        if module['id'] == 'multi_step' and 'connected-cases/multi_step.json' in package.manifest.artifacts:
            from .multi_step_case import load_multi_step_case
            item['connectedWorkflowAssessment'] = load_multi_step_case(package).public_definition()
            item['assessment'] = None
        if module['id'] == 'validation_qa' and 'validation-cases/validation_qa.json' in package.manifest.artifacts:
            from .validation_case import load_validation_case
            item['validationAssessment'] = load_validation_case(package).public_definition()
        if module['id'] == 'governance' and 'governance-cases/governance.json' in package.manifest.artifacts:
            from .governance_case import load_governance_case
            item['governanceAssessment'] = load_governance_case(package).public_definition()
        if module['id'] == 'batch_processing' and 'batch-cases/batch_processing.json' in package.manifest.artifacts:
            from .batch_case import load_batch_case
            item['batchAssessment'] = load_batch_case(package).public_definition()
            item['assessment'] = None
        if module['id'] == 'output_delivery' and 'output-cases/output_delivery.json' in package.manifest.artifacts:
            from .output_case import load_output_case
            item['outputWorkflowAssessment'] = load_output_case(package).public_definition()
            item['assessment'] = None
        if module['id'] == 'advanced_nodes' and 'advanced-cases/advanced_nodes.json' in package.manifest.artifacts:
            from .advanced_case import load_advanced_case
            item['budgetWorkflowAssessment'] = load_advanced_case(package).public_definition()
            item['assessment'] = None
        if module['id'] == 'workflow_design' and 'design-cases/workflow_design.json' in package.manifest.artifacts:
            from .workflow_design_case import load_workflow_design_case
            item['workflowDesignAssessment'] = load_workflow_design_case(package).public_definition()
            item['assessment'] = None
        if decision_path in package.manifest.artifacts:
            from .learner_decisions import load_prompt
            item['decisionPrompts'] = [{**prompt.model_dump(mode='json'), 'prompt_sha256': prompt.digest}
                for prompt in (load_prompt(package, module['id'], raw['id']) for raw in package.json(decision_path))]
            item['assessment'] = None
            if ((module['id'] == 'foundations' and 'proposals/foundations.json' in package.manifest.artifacts)
                    or (module['id'] == 'extraction_engine' and 'repair-cases/extraction_engine.json' in package.manifest.artifacts)):
                from .practical_preparation import PracticalPreparation
                PracticalPreparation.eligible(package, module['id'])
                item['practicalPreparation'] = True
            if module['id'] == 'extraction_engine' and 'repair-cases/extraction_engine.json' in package.manifest.artifacts:
                from .repair_case import load_repair_case
                item['repairAssignment'] = load_repair_case(package, module['id']).public_definition()
        modules.append(item)
    return modules


class CourseDelivery:
    def __init__(self, repository: EnrollmentRepository | None = None):
        self.repository = repository or EnrollmentRepository()

    async def _resolve(self, user_id: str, enrollment_id: str):
        enrollment = await self.repository._enrollment(user_id, enrollment_id)
        package = self.repository.catalog.load(enrollment.course_version)
        progress = await self.repository.read_progress(user_id, enrollment_id)
        return enrollment, package, progress

    async def course(self, user_id: str, enrollment_id: str) -> dict:
        from .bridge_path import public_bridge_path
        from .progression_policy import public_progression_policy
        from .credential_scope import public_credential_scope
        enrollment, package, progress = await self._resolve(user_id, enrollment_id)
        modules = public_modules(package)
        completed = sum(bool(progress.modules.get(module.id, {}).get('completed')) for module in package.manifest.modules)
        return {
            **package.summary(), 'enrollment_id': enrollment.uuid,
            'provenance': enrollment.provenance, 'enrollment_state': enrollment.state,
            'transition_policy': 'optional', 'modules': modules,
            'modules_completed': completed, 'progress': progress.model_dump(mode='json'),
            'selected_outcome_completion': selected_outcome_completion_available(package),
            'progression_policy': public_progression_policy(package),
            'credential_scope': public_credential_scope(package),
            'bridge_path': public_bridge_path(package),
        }

    @staticmethod
    def _lesson(package, module_id: str, lesson_id: str) -> tuple[dict, int, int]:
        if module_id not in {module.id for module in package.manifest.modules}:
            raise CourseCatalogError('Module is not part of this enrollment')
        lessons = package.json('lessons.json')[module_id]['lessons']
        for position, lesson in enumerate(lessons, 1):
            if lesson['id'] == lesson_id:
                return lesson, position, len(lessons)
        raise CourseCatalogError('Lesson is not part of this enrollment')

    async def lesson(self, user_id: str, enrollment_id: str, module_id: str, lesson_id: str) -> dict:
        enrollment, package, _progress = await self._resolve(user_id, enrollment_id)
        lesson, position, count = self._lesson(package, module_id, lesson_id)
        return {
            **lesson, 'enrollment_id': enrollment.uuid, 'course_version': enrollment.course_version,
            'manifest_sha256': package.manifest_sha256, 'module_id': module_id,
            'lesson_number': position, 'lesson_count': count,
        }

    @staticmethod
    async def store_position(progress, package, module_id: str, lesson_id: str, expected_revision: int) -> dict:
        """Called only inside a pinned write boundary; stale devices fail closed."""
        if progress.position_revision != expected_revision:
            raise EnrollmentConflict('Your saved place changed in another session; reload before saving it again')
        lesson, _position, _count = CourseDelivery._lesson(package, module_id, lesson_id)
        position = {
            'module_id': module_id, 'lesson_id': lesson_id, 'revision': lesson['revision'],
            'content_sha256': hashlib.sha256(lesson['content'].encode()).hexdigest(),
            'saved_at': datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        }
        # Navigation is independent from earned credit, reflections and labs.
        # The selection write boundary serializes all course mutations.
        result = await CertificationProgress.get_motor_collection().update_one(
            {**progress_filter(progress), 'position_revision': expected_revision} if expected_revision else {
                **progress_filter(progress), '$or': [{'position_revision': 0}, {'position_revision': {'$exists': False}}]},
            {'$set': {
                f'modules.{module_id}.learning_position': position,
                'learning_position': position, 'position_revision': expected_revision + 1,
            }},
        )
        if result.matched_count != 1:
            raise EnrollmentConflict('The write boundary or saved position changed; reload before saving again')
        progress.learning_position = position
        progress.position_revision = expected_revision + 1
        progress.modules.setdefault(module_id, {})['learning_position'] = position
        return {
            'saved': True, 'enrollment_id': progress.enrollment_id, 'course_version': progress.course_version,
            'learning_position': position, 'position_revision': progress.position_revision,
            **position,
        }

    async def save_position(self, user_id: str, enrollment_id: str, module_id: str, lesson_id: str, *, expected_revision: int | None = None) -> dict:
        async with self.repository.write_boundary(user_id, enrollment_id, operation='save_lesson_position') as progress:
            package = self.repository.catalog.load(progress.course_version)
            return await self.store_position(
                progress, package, module_id, lesson_id,
                progress.position_revision if expected_revision is None else expected_revision,
            )

    async def validate(self, user_id: str, enrollment_id: str, module_id: str) -> dict:
        # Grading may await workspace reads. Keep activation out until it ends;
        # the rubric and progress stay pinned for the entire async operation.
        async with self.repository.write_boundary(user_id, enrollment_id, operation='validate:' + module_id) as progress:
            package = self.repository.catalog.load(progress.course_version)
            return {'enrollment_id': enrollment_id, **await grade(package, progress, module_id)}
