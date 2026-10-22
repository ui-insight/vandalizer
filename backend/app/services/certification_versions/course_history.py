"""Discover owned practical history without selecting or initializing a course."""
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict, EnrollmentRepository
from .learner_decisions import load_prompt


class CourseHistory:
    def __init__(self, repository=None):
        self.repository = repository or EnrollmentRepository()

    async def selection(self, user_id):
        return await self.repository.selections.find_one({'user_id': user_id},
            {'_id': 0, 'active_enrollment_id': 1, 'revision': 1, 'pending_transition_id': 1})

    @staticmethod
    def selection_status(enrollment_id, state, selection):
        if (selection or {}).get('active_enrollment_id') == enrollment_id:
            return 'confirmation_pending' if selection.get('pending_transition_id') else 'current'
        return 'prepared' if state == 'prepared' else 'retained'

    async def courses(self, user_id):
        selection = await self.selection(user_id)
        rows = await self.repository.enrollments.find({'user_id': user_id}, {
            '_id': 0, 'uuid': 1, 'course_version': 1, 'manifest_sha256': 1,
            'state': 1, 'created_at': 1, 'provenance': 1,
        }).sort([('created_at', -1), ('uuid', -1)]).limit(51).to_list(51)
        courses = []
        for row in rows[:50]:
            title, available = 'Saved course', False
            try:
                package = self.repository.catalog.load(row['course_version'])
                if package.manifest_sha256 == row['manifest_sha256']:
                    title, available = package.manifest.title, True
            except CourseCatalogError:
                # Preserve discoverability of the owned reference without
                # substituting another package for unavailable original work.
                pass
            courses.append({
                'enrollment_id': row['uuid'], 'course_version': row['course_version'],
                'course_title': title, 'enrollment_state': row['state'],
                'provenance': row.get('provenance'),
                'selection_status': self.selection_status(row['uuid'], row['state'], selection),
                'created_at': row.get('created_at'), 'definition_available': available,
            })
        if await self.selection(user_id) != selection:
            raise EnrollmentConflict('The selected course changed while history was loading; refresh its status')
        return {'courses': courses, 'older_courses_available': len(rows) > 50,
                'read_only': True}

    async def course(self, user_id, enrollment_id):
        selection = await self.selection(user_id)
        enrollment = await self.repository._enrollment(user_id, enrollment_id)
        package = self.repository.catalog.load(enrollment.course_version)
        modules = []
        for module in package.manifest.modules:
            path = f'decisions/{module.id}.json'
            scenario_path = f'assessments/{module.id}.json'
            process_path = f'process-cases/{module.id}.json'
            design_path = f'design-cases/{module.id}.json'
            connected_path = f'connected-cases/{module.id}.json'
            budget_path = f'advanced-cases/{module.id}.json'
            validation_path = f'validation-cases/{module.id}.json'
            batch_path = f'batch-cases/{module.id}.json'
            governance_path = f'governance-cases/{module.id}.json'
            output_path = f'output-cases/{module.id}.json'
            if not any(asset in package.manifest.artifacts for asset in (path, scenario_path, process_path, design_path, connected_path, budget_path, output_path, validation_path, batch_path, governance_path)):
                continue
            prompts = [load_prompt(package, module.id, raw['id']) for raw in package.json(path)] if path in package.manifest.artifacts else []
            scenario = None
            if scenario_path in package.manifest.artifacts:
                from .scenario_submissions import module_bank
                scenario = module_bank(package, module.id).public_definition()
            process = None
            if process_path in package.manifest.artifacts:
                from .process_case import load_process_case
                process = load_process_case(package, module.id).public_definition()
            design = None
            if design_path in package.manifest.artifacts:
                from .workflow_design_case import load_workflow_design_case
                design = load_workflow_design_case(package).public_definition()
            connected = None
            if connected_path in package.manifest.artifacts:
                from .multi_step_case import load_multi_step_case
                connected = load_multi_step_case(package).public_definition()
            budget = None
            if budget_path in package.manifest.artifacts:
                from .advanced_case import load_advanced_case
                budget = load_advanced_case(package).public_definition()
            output = None
            if output_path in package.manifest.artifacts:
                from .output_case import load_output_case
                output = load_output_case(package).public_definition()
            governance = None
            if module.id == 'governance' and 'governance-cases/governance.json' in package.manifest.artifacts:
                from .governance_case import load_governance_case
                governance = load_governance_case(package).public_definition()
            batch = None
            if batch_path in package.manifest.artifacts:
                from .batch_case import load_batch_case
                batch = load_batch_case(package).public_definition()
            validation = None
            if validation_path in package.manifest.artifacts:
                from .validation_case import load_validation_case
                validation = load_validation_case(package).public_definition()
            modules.append({'module_id': module.id, 'title': module.title, 'workflow_design_definition': design,
                            'connected_workflow_definition': connected,
                            'budget_workflow_definition': budget,
                            'output_workflow_definition': output,
                            'validation_definition': validation, 'batch_definition': batch, 'governance_definition': governance,
                            'process_definition': process,
                            'scenario_definition': scenario,
                            'decision_prompts': [{**prompt.model_dump(mode='json'),
                                                  'prompt_sha256': prompt.digest} for prompt in prompts]})
        if await self.selection(user_id) != selection:
            raise EnrollmentConflict('The selected course changed while history was loading; refresh its status')
        return {'enrollment_id': enrollment.uuid, 'course_version': enrollment.course_version,
                'course_title': package.manifest.title, 'manifest_sha256': package.manifest_sha256,
                'enrollment_state': enrollment.state, 'provenance': enrollment.provenance,
                'selection_status': self.selection_status(enrollment.uuid, enrollment.state, selection),
                'read_only': True, 'modules': modules}
