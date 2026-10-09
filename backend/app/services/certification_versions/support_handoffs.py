"""Expose terminal private training handoffs without files, memos or dispatch."""
from app.models.certification import CertificationLearnerDecision
from .catalog import CourseCatalogError
from .governance_handoff import GovernanceHandoffRepository
from .output_private_handoff import OutputPrivateHandoffRepository, PROMPT_ID

STEPS = {
    'failed': 'The controlled training handoff stopped before writing a destination copy. Generation is preserved. The learner can inspect this exact failed receipt and retry only its approved private handoff.',
    'delivered': 'The approved copy is saved in the learner’s private training inbox. This is not sponsor delivery, external email or broader sharing.',
}


async def support_handoffs(enrollment, package):
    from .support_operations import reference
    identity = {'user_id': enrollment.user_id, 'enrollment_id': enrollment.uuid}
    journals = {PROMPT_ID: OutputPrivateHandoffRepository, GovernanceHandoffRepository.prompt_id: GovernanceHandoffRepository}
    records = CertificationLearnerDecision.get_motor_collection()
    rows = await records.find({**identity, 'prompt_id': {'$in': list(journals)}}, {'_id': 1}).sort('_id', -1).limit(6).to_list(6)
    modules = {module.id: module for module in package.manifest.modules}
    group = {'kind': 'private_handoff', 'records': [], 'more_pending': False, 'more_recent': len(rows) > 5}
    for marker in rows[:5]:
        try:
            # Fetch and decode one bounded receipt at a time. Embedded file copies
            # can be large; never retain a list of all private file payloads.
            raw = await records.find_one({**identity, '_id': marker['_id']})
            saved = journals[raw['prompt_id']].decode(raw)
            if (saved['module_id'] not in modules or any(saved.get(key) != value for key, value in {
                    **identity, 'course_version': enrollment.course_version, 'manifest_sha256': package.manifest_sha256}.items())):
                raise CourseCatalogError('Original handoff course needs reconciliation')
            references = {'run_id': reference(saved['run_id'])}
            for key in ('review_id', 'release_id', 'previous_failed_id'):
                if saved['submission'].get(key) is not None:
                    references[key] = reference(saved['submission'][key])
            group['records'].append({'request_id': reference(saved['uuid']), 'module_id': saved['module_id'],
                'module_title': modules[saved['module_id']].title, 'state': saved['status'],
                'next_step': STEPS[saved['status']], 'references': references, 'failed_required_outcomes': []})
        except (CourseCatalogError, KeyError, TypeError, ValueError, AttributeError):
            group['records'].append({'state': 'unavailable', 'next_step': 'The original private handoff needs reconciliation. No delivery, files or safe retry is inferred.'})
    return group
