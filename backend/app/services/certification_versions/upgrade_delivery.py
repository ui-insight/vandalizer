"""Learner-facing optional choices over the verified preservation journals.

Reads never accept or activate a choice. Stable original request references
allow another device to resume the same reviewed intent after a lost reply.
"""
from uuid import NAMESPACE_URL, uuid5

from bson import ObjectId

from .attempts import AttemptRepository, encode
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict, EnrollmentRepository
from .grading import selected_outcome_completion_available
from .saved_course_selection import SavedCourseSelectionRepository, SavedCourseSelectionRequest
from .selection_delivery import SelectionDelivery
from .transition_preview import TransitionPreview
from .upgrade_activation import UpgradeActivationRepository, UpgradeActivationRequest
from .upgrade_comparison import UpgradeComparison, UpgradeUnavailable
from .upgrade_decisions import UpgradeDecisionRepository, UpgradeDecisionRequest


def stable_request(user_id, kind, digest):
    return uuid5(NAMESPACE_URL, f'vandalizer:certification:{kind}:{user_id}:{digest}').hex


class UpgradeDelivery:
    def __init__(self, repository=None):
        self.repository = repository or EnrollmentRepository()
        self.decisions = UpgradeDecisionRepository(self.repository)
        self.activations = UpgradeActivationRepository(self.repository)
        self.saved = SavedCourseSelectionRepository(self.repository)

    async def existing_started_course(self, user_id, version, *, excluding=None):
        return await self.repository.enrollments.find_one({'user_id': user_id, 'course_version': version,
            'state': {'$ne': 'prepared'}, **({'uuid': {'$ne': excluding}} if excluding else {})})

    async def decision_view(self, record):
        request = record.request
        raw = await self.activations.records.find_one({'decision_id': request.request_id, 'user_id': record.user_id})
        if raw:
            self.activations.decode(raw)
        activation_id = raw['uuid'] if raw else stable_request(record.user_id, 'activate-choice', request.request_id)
        return {'decision_id': request.request_id, 'source_enrollment_id': request.source_enrollment_id,
            'target_version': request.target_version, 'preview_sha256': request.preview_sha256,
            'target_manifest_sha256': record.preview['target']['manifest_sha256'],
            'decision_sha256': encode(record.model_dump(mode='json'))[1], 'accepted_at': record.accepted_at,
            'credit_transferred': False, 'requires_fresh_activation_check': True,
            'activation_request': UpgradeActivationRequest(request_id=activation_id, decision_id=request.request_id,
                consent='activate_optional_upgrade_preserving_original_work_without_credit_transfer').model_dump(mode='json')}

    async def preview(self, user_id, source_id, target_version):
        comparison = UpgradeComparison(self.repository)
        public = await comparison.inspect(user_id, source_id, target_version)
        snapshot = await TransitionPreview(self.repository).inspect(user_id, source_id, target_version)
        if snapshot['preview_sha256'] != public['preview_sha256']:
            raise EnrollmentConflict('Course work changed while reviewing the optional choice; refresh the comparison')
        # An unchanged semantic choice may have an older ownership fence in
        # its original preview. Reuse its exact request, never rewrite consent.
        original = None
        indexed = await self.decisions.records.find_one({'user_id': user_id, 'source_enrollment_id': source_id,
            'target_version': target_version, 'decision_basis_sha256': snapshot['decision_basis_sha256']}, sort=[('_id', -1)])
        if indexed:
            original = self.decisions.decode(indexed)
            if original.preview['preservation_plan'] != snapshot['preservation_plan']:
                raise CourseCatalogError('The original preservation choice has inconsistent saved-work metadata')
        # Older internal records remain readable without rewriting their
        # immutable consent or requiring a data migration during this GET.
        legacy = self.decisions.records.find({'user_id': user_id, 'source_enrollment_id': source_id, 'target_version': None}).sort('_id', -1)
        async for raw in legacy:
            if original:
                break
            candidate = self.decisions.decode(raw)
            if (candidate.request.target_version == target_version
                    and candidate.preview.get('decision_basis_sha256') == snapshot['decision_basis_sha256']
                    and candidate.preview['preservation_plan'] == snapshot['preservation_plan']):
                original = candidate
                break
        request = original.request if original else UpgradeDecisionRequest(
            request_id=stable_request(user_id, 'preserve-choice', snapshot['preview_sha256']),
            source_enrollment_id=source_id, target_version=target_version, preview_sha256=snapshot['preview_sha256'],
            consent='preserve_original_work_and_require_all_new_outcomes')
        source = await comparison.source(user_id, source_id)
        package, _ = comparison.target(source.course_version, target_version)
        selection = await self.repository.selections.find_one({'user_id': user_id})
        if not selection or selection['active_enrollment_id'] != source_id:
            raise EnrollmentConflict('The selected course changed during review')
        reason = None
        if source.state not in ('active', 'completed'):
            reason = 'source_read_only'
        elif not selected_outcome_completion_available(package):
            reason = 'assessment_unavailable'
        elif await self.existing_started_course(user_id, target_version):
            reason = 'resume_saved_course'
        elif selection.get('in_flight_writes') or selection.get('pending_transition_id'):
            reason = 'selection_busy'
        elif snapshot['preservation_plan']['reconciliation_required_count'] or any(
                item['code'] in ('pending_assessment', 'unfinished_recovery', 'credential_preservation') for item in snapshot['blockers']):
            reason = 'unfinished_course_work'
        return {'comparison': public, 'choice': {'available': reason is None, 'reason': reason,
            'request': request.model_dump(mode='json'), 'recorded': original is not None,
            'decision': await self.decision_view(original) if original else None}}

    async def accept(self, user_id, body):
        request = UpgradeDecisionRequest.model_validate(body)
        existing = await self.decisions.records.find_one({'uuid': request.request_id})
        if existing is None:
            if request.request_id != stable_request(user_id, 'preserve-choice', request.preview_sha256):
                raise EnrollmentConflict('Use the original request from the reviewed optional course comparison')
            if await self.existing_started_course(user_id, request.target_version):
                raise EnrollmentConflict('Resume your saved course for this version instead of creating another enrollment')
        record = await self.decisions.accept(user_id, request)
        return await self.decision_view(record)

    async def decision(self, user_id, request_id):
        record = await self.decisions.get(user_id, request_id)
        if record is None:
            raise UpgradeUnavailable('The original saved course choice is unavailable')
        return await self.decision_view(record)

    async def activation(self, user_id, request_id):
        raw = await self.activations.records.find_one({'uuid': request_id, 'user_id': user_id})
        if raw is None:
            raise UpgradeUnavailable('The original course-switch request is unavailable')
        intent = self.activations.decode(raw)
        selected = await self.repository.selections.find_one({'user_id': user_id})
        return {'request': intent['request'], 'source_enrollment_id': intent['source_enrollment_id'],
            'state': raw['state'], 'read_only': True,
            'current_enrollment_id': (selected or {}).get('active_enrollment_id'),
            'confirmation_pending': (selected or {}).get('pending_transition_id') == request_id,
            'receipt': SelectionDelivery.summary(AttemptRepository.payload(raw, 'result'), raw['uuid']) if raw['state'] == 'applied' else None}

    async def result(self, user_id, receipt, request_id):
        selected = await self.repository.selections.find_one({'user_id': user_id})
        return {'receipt': SelectionDelivery.summary(receipt, request_id),
                'current_enrollment_id': (selected or {}).get('active_enrollment_id'),
                'confirmation_pending': (selected or {}).get('pending_transition_id') == request_id}

    async def activate(self, user_id, body):
        request = UpgradeActivationRequest.model_validate(body)
        record = await self.decisions.get(user_id, request.decision_id)
        if record is None:
            raise UpgradeUnavailable('The original saved course choice is unavailable')
        existing = await self.activations.owned(user_id, request)
        excluding = self.activations.decode(existing)['target']['target_enrollment_id'] if existing else None
        if await self.existing_started_course(user_id, record.request.target_version, excluding=excluding):
            raise EnrollmentConflict('Resume the existing saved course instead of starting a second enrollment')
        receipt = await self.activations.activate(user_id, request)
        return await self.result(user_id, receipt, request.request_id)

    async def saved_options(self, user_id, *, cursor=None):
        selection = await self.repository.selections.find_one({'user_id': user_id})
        current_id = (selection or {}).get('active_enrollment_id')
        if not current_id:
            return {'current_enrollment_id': None, 'courses': [], 'next_cursor': None, 'read_only': True}
        query = {'user_id': user_id, 'state': 'applied', **({'_id': {'$lt': ObjectId(cursor)}} if cursor else {})}
        rows = await self.activations.records.find(query).sort('_id', -1).limit(51).to_list(51)
        courses = []
        for raw in rows[:50]:
            self.activations.decode(raw)
            receipt = AttemptRepository.payload(raw, 'result')
            if current_id == receipt['target_enrollment_id']:
                destination, action = receipt['source_enrollment_id'], 'return_to_original_course'
            elif current_id == receipt['source_enrollment_id']:
                destination, action = receipt['target_enrollment_id'], 'resume_upgraded_course'
            else:
                continue
            owned = await self.repository.enrollments.find_one({'uuid': destination, 'user_id': user_id})
            if owned is None:
                raise EnrollmentConflict('The original saved enrollment is unavailable')
            title, available = 'Saved course', False
            try:
                package = self.repository.catalog.load(owned['course_version'])
                if package.manifest_sha256 == owned['manifest_sha256']:
                    title, available = package.manifest.title, True
            except CourseCatalogError:
                pass
            courses.append({'activation_id': raw['uuid'], 'action': action, 'enrollment_id': destination,
                'course_version': owned['course_version'], 'course_title': title, 'definition_available': available})
        if await self.repository.selections.find_one({'user_id': user_id}) != selection:
            raise EnrollmentConflict('The selected course changed while saved choices were loading')
        return {'current_enrollment_id': current_id, 'courses': courses, 'read_only': True,
                'next_cursor': str(rows[49]['_id']) if len(rows) > 50 else None}

    async def saved_preview(self, user_id, activation_id, action):
        preview = await self.saved.preview(user_id, activation_id, action)
        request = SavedCourseSelectionRequest(request_id=stable_request(user_id, 'select-saved-course', preview['preview_sha256']),
            activation_id=activation_id, action=action, preview_sha256=preview['preview_sha256'],
            consent='select_saved_course_preserving_both_histories_and_credit')
        return {'preview': preview, 'request': request.model_dump(mode='json')}

    async def select_saved(self, user_id, body):
        request = SavedCourseSelectionRequest.model_validate(body)
        receipt = await self.saved.select(user_id, request)
        return await self.result(user_id, receipt, request.request_id)

    async def saved_selection(self, user_id, request_id):
        raw = await self.saved.records.find_one({'uuid': request_id, 'user_id': user_id})
        if raw is None:
            raise UpgradeUnavailable('The original saved-course selection is unavailable')
        intent = self.saved.decode(raw)
        selected = await self.repository.selections.find_one({'user_id': user_id})
        return {'request': intent['request'], 'source_enrollment_id': intent['preview']['source']['enrollment_id'],
            'state': raw['state'], 'read_only': True,
            'current_enrollment_id': (selected or {}).get('active_enrollment_id'),
            'confirmation_pending': (selected or {}).get('pending_transition_id') == request_id,
            'receipt': SelectionDelivery.summary(AttemptRepository.payload(raw, 'result'), request_id) if raw['state'] == 'applied' else None}
