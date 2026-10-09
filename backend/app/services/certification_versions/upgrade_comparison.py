"""Learner-facing read-only comparisons of explicitly offered published courses.

No enrollment initialization, decisions, transfers or activation occur here.
Internal draft planning stays separate from this published-course boundary.
"""
from .enrollments import EnrollmentConflict, EnrollmentRepository
from .outcomes import package_outcomes
from .transition_preview import TransitionPreview


class UpgradeUnavailable(ValueError):
    pass


class UpgradeComparison:
    def __init__(self, repository=None):
        self.repository = repository or EnrollmentRepository()

    async def source(self, user_id, enrollment_id):
        enrollment = await self.repository.current(user_id)
        if enrollment is None or enrollment.uuid != enrollment_id:
            raise EnrollmentConflict('The selected course changed; refresh your course before comparing versions')
        return enrollment

    def target(self, source_version, target_version):
        catalog = self.repository.catalog
        registry = catalog.registry()
        if (target_version not in registry.get('optional_upgrade_offers', {}).get(source_version, [])
                or registry['releases'][target_version]['state'] != 'published'):
            raise UpgradeUnavailable('This course comparison is not available')
        package = catalog.load(target_version, new_enrollment=True)
        contract = package_outcomes(package)
        if contract is None:
            raise UpgradeUnavailable('This course comparison is not available')
        return package, contract

    async def options(self, user_id, enrollment_id):
        source = await self.source(user_id, enrollment_id)
        versions = self.repository.catalog.registry().get('optional_upgrade_offers', {}).get(source.course_version, [])
        offered = []
        for version in versions:
            try:
                package, contract = self.target(source.course_version, version)
            except UpgradeUnavailable:
                continue
            offered.append({**package.summary(), 'description': package.manifest.description,
                            'required_outcome_count': len(contract.required_outcomes())})
        await self.source(user_id, enrollment_id)
        return {'enrollment_id': enrollment_id, 'policy': 'optional', 'can_activate': False, 'courses': offered}

    async def inspect(self, user_id, enrollment_id, target_version):
        source = await self.source(user_id, enrollment_id)
        target, _ = self.target(source.course_version, target_version)
        preview = await TransitionPreview(self.repository).inspect(user_id, enrollment_id, target_version)
        # An offer may be withdrawn while the source work is being inspected.
        current_target, _ = self.target(source.course_version, target_version)
        if (target.manifest_sha256 != current_target.manifest_sha256
                or preview['target']['manifest_sha256'] != target.manifest_sha256):
            raise EnrollmentConflict('The offered course changed; refresh the comparison')
        source_package = self.repository.catalog.load(source.course_version)
        titles = {module.id: module.title for module in source_package.manifest.modules}
        original = preview['source']
        needs_attention = {blocker['code'] for blocker in preview['blockers']}
        work = [
            ('pending_assessments', 'Unfinished assessment results'),
            ('saved_completion_history', 'Original completion results'),
            ('saved_recovery_history', 'Saved recovery records'),
            ('prepared_labs', 'Saved lab inputs'),
            ('saved_scenarios', 'Saved scenario submissions'),
            ('saved_lab_runs', 'Saved lab runs'),
            ('saved_automatic_reviews', 'Saved automatic reviews'),
            ('saved_learner_decisions', 'Saved learner decisions'),
            ('saved_process_designs', 'Saved process designs'),
            ('saved_workflow_designs', 'Saved workflow approvals'),
        ]
        return {
            'policy': 'optional', 'can_activate': False, 'preview_sha256': preview['preview_sha256'],
            'source': {
                'enrollment_id': enrollment_id, 'course_version': source.course_version,
                'course_title': source_package.manifest.title, 'provenance': original['provenance'],
                'total_xp': original['total_xp'], 'certified': original['certified'],
                'credential_preserved': original['credential_id'] is not None,
                'completed_modules': [{**item, 'title': titles.get(item['module_id'], item['module_id'])}
                                      for item in original['preserved_module_credit']],
                'has_saved_place': original['learning_position'] is not None,
            },
            'target': {
                'course_version': target_version, 'course_title': target.manifest.title,
                'manifest_sha256': target.manifest_sha256,
                'required_outcome_count': preview['target']['required_outcome_count'],
                'transferred_outcome_count': preview['target']['transferred_outcome_count'],
                'modules': preview['target']['modules'],
            },
            'preservation_plan': preview['preservation_plan'],
            'equivalence_plan': preview['equivalence_plan'],
            'saved_work': [{'kind': key, 'label': label, 'count': len(preview[key])} for key, label in work if preview[key]],
            'work_in_flight': 'write_in_flight' in needs_attention,
            'unfinished_answers': 'unfinished_answers' in needs_attention,
            'credential_needs_preservation': 'credential_preservation' in needs_attention,
        }
