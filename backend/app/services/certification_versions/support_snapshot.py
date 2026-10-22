"""Read-only support metadata without reflection text, source data or grading."""
import datetime
import hashlib
import re
from types import SimpleNamespace

from .attempts import AttemptRepository, progress_digest
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict, EnrollmentRepository
from .outcomes import package_outcomes

STATES = {
    'evaluating': 'Completion is not confirmed. Inspect the original request before retrying.',
    'graded': 'The original grade is saved; completion is not yet confirmed. Recover that same request.',
    'applied': 'Credit was recorded. Reopening the result does not award more XP.',
    'rejected': 'Required checks were not met. Open the original feedback, revise the evidence and submit a new assessment.',
    'failed': 'A technical completion failure was recorded. Inspect the original request; this is not proof of a learner failure.',
}


def recorded_time(value):
    if isinstance(value, datetime.datetime):
        return value.isoformat()
    if isinstance(value, str):
        try:
            return datetime.datetime.fromisoformat(value).isoformat()
        except ValueError:
            pass
    return None


def progress_modules(progress, module_ids):
    """The admin detail needs earned-state fields, never arbitrary module blobs."""
    result = {}
    for module_id in module_ids:
        module = progress.modules.get(module_id)
        if not isinstance(module, dict):
            continue
        item = {key: module[key] for key in ('stars', 'attempts', 'xp_earned')
                if type(module.get(key)) is int and module[key] >= 0}
        if type(module.get('completed')) is bool:
            item['completed'] = module['completed']
        if 'completed_at' in module:
            item['completed_at'] = recorded_time(module['completed_at'])
        result[module_id] = item
    return result


def completion_validation(journal, row):
    """Receipt state alone cannot establish an intact recorded completion."""
    state = row['state']
    validation = None
    if state in ('graded', 'applied', 'rejected') or row.get('validation_json') is not None or row.get('validation_sha256') is not None:
        validation = journal.payload(row, 'validation')
        if type(validation.get('passed')) is not bool or not isinstance(validation.get('checks'), list):
            raise CourseCatalogError('Original validation is unavailable')
    if state in ('applied', 'rejected', 'failed'):
        result = journal.payload(row, 'result')
        if result.get('attempt_id') != row['uuid']:
            raise CourseCatalogError('Original completion result identity changed')
        if state == 'applied':
            if (result.get('error') or validation['passed'] is not True
                    or result.get('validation') != validation
                    or any(result.get(key) != row[key] for key in ('module_id', 'enrollment_id', 'course_version', 'manifest_sha256'))):
                raise CourseCatalogError('Original awarded result changed')
        elif state == 'rejected':
            if not isinstance(result.get('error'), str) or not result['error'] or validation['passed'] is not False or result.get('validation') != validation:
                raise CourseCatalogError('Original rejected result changed')
        elif result.get('failure_kind') != 'execution' or not isinstance(result.get('error'), str) or not result['error']:
            raise CourseCatalogError('Original technical failure changed')
    elif row.get('result_json') is not None or row.get('result_sha256') is not None:
        raise CourseCatalogError('Unfinished completion has an unexpected result')
    return validation


async def support_snapshot(progress, metadata, *, repository=None):
    result = {
        'observed_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'read_only': True, 'last_saved_lesson': None,
        'position_status': 'not_recorded', 'pending_credential': progress.pending_credential is not None,
        'pending_completions': [], 'recent_completions': [], 'older_completions_available': False,
        'operations': None,
        'explanation': 'Recorded state only. Refresh for current status; opening this view does not retry, grade or change a course.',
    }
    if metadata.get('reconciliation_error'):
        result.update(position_status='unavailable', explanation='The course binding needs reconciliation before its saved state can be interpreted.')
        return result
    repo = repository or EnrollmentRepository()
    from .support_access import access_history
    result['access_changes'] = await access_history(repo, progress)
    enrollment_id = metadata.get('enrollment_id')
    if not enrollment_id:
        result['explanation'] = 'Historical course version is unknown. Reading position may exist only in the learner’s browser; no server assessment history is inferred.'
        return result
    enrollment = await repo._enrollment(progress.user_id, enrollment_id)
    package = repo.catalog.load(enrollment.course_version)
    if (str(progress.id) != enrollment.progress_id or enrollment.manifest_sha256 != package.manifest_sha256
            or progress.enrollment_id not in (None, enrollment_id)
            or progress.course_version not in (None, enrollment.course_version)):
        raise EnrollmentConflict('Support progress no longer matches its original course')
    result['manifest_sha256'] = package.manifest_sha256
    modules = {module.id: module for module in package.manifest.modules}
    position = progress.learning_position
    if position:
        lessons = package.json('lessons.json')
        module = modules.get(position.get('module_id')) if isinstance(position.get('module_id'), str) else None
        lesson = next((item for item in lessons[module.id]['lessons']
                       if item['id'] == position.get('lesson_id')), None) if module else None
        if (lesson and type(position.get('revision')) is int and lesson['revision'] == position.get('revision')
                and hashlib.sha256(lesson['content'].encode()).hexdigest() == position.get('content_sha256')):
            result.update(position_status='saved', last_saved_lesson={
                'module_id': module.id, 'module_title': module.title,
                'lesson_id': lesson['id'], 'lesson_title': lesson['title'],
                'revision': lesson['revision'], 'saved_at': recorded_time(position.get('saved_at')),
            })
        else:
            result['position_status'] = 'unavailable'
    journal = AttemptRepository()
    operation = SimpleNamespace(user_id=progress.user_id, progress=SimpleNamespace(enrollment_id=enrollment_id), package=package)
    # The journal verifies pending course/rubric identity; viewing old history
    # must not attribute a different selected enrollment's worker to this one.
    pending = await journal.pending(operation)
    for item in pending:
        if not isinstance(item.get('attempt_id'), str) or not re.fullmatch(r'[a-f0-9]{32}', item['attempt_id']):
            raise CourseCatalogError('Pending completion identity needs reconciliation')
        raw = await journal.records.find_one({'uuid': item['attempt_id'], 'user_id': progress.user_id, 'enrollment_id': enrollment_id})
        if raw is not None and raw.get('state') in ('applied', 'rejected', 'failed'):
            continue  # Finished since the pending read; refresh shows its history.
        next_step = STATES.get(item['state'], 'Multiple unfinished requests need reconciliation before another completion.')
        try:
            if raw is None:
                raise CourseCatalogError('Original pending request is unavailable')
            completion_validation(journal, raw)
        except (CourseCatalogError, KeyError, TypeError, ValueError):
            item = {**item, 'state': 'review'}
            next_step = 'The unfinished completion record needs reconciliation; no saved grade or safe retry is inferred.'
        result['pending_completions'].append({**item,
            'in_flight': bool(item['in_flight'] and metadata.get('is_active')),
            'module_title': modules[item['module_id']].title,
            'next_step': next_step,
        })
    projection = {key: 1 for key in ('uuid', 'module_id', 'course_version', 'manifest_sha256', 'rubric_id',
        'state', 'created_at', 'progress_sha256', 'assessment_selection_json', 'assessment_selection_sha256',
        'validation_json', 'validation_sha256', 'result_json', 'result_sha256', 'enrollment_id')}
    rows = await journal.records.find({'user_id': progress.user_id, 'enrollment_id': enrollment_id}, projection).sort(
        [('created_at', -1), ('uuid', -1)]).limit(11).to_list(11)
    result['older_completions_available'] = len(rows) > 10
    contract = package_outcomes(package)
    required = {module.module_id: {outcome.id: outcome.statement for outcome in module.outcomes}
                for module in contract.modules} if contract else {}
    for row in rows[:10]:
        try:
            if (not re.fullmatch(r'[a-f0-9]{32}', row.get('uuid', '')) or row.get('module_id') not in modules
                    or row.get('state') not in STATES
                    or (row.get('course_version'), row.get('manifest_sha256'), row.get('rubric_id')) != (
                        enrollment.course_version, package.manifest_sha256, package.manifest.rubric_id)):
                raise CourseCatalogError('Original completion metadata is unavailable')
            selected = journal.assessment_selection(row) or {}
            failed = []
            validation = completion_validation(journal, row)
            if validation is not None:
                definitions = required.get(row['module_id'], {})
                failed = [{'outcome_id': check['id'], 'statement': definitions[check['id']]}
                          for check in validation['checks'] if isinstance(check, dict)
                          and check.get('passed') is False and check.get('id') in definitions]
            next_step = STATES[row['state']]
            if (row['state'] == 'graded' and row.get('progress_sha256') != progress_digest(progress)
                    and (progress.completion_receipt or {}).get('attempt_id') != row['uuid']):
                next_step = 'Saved answers or credit changed after grading. Reconcile the original request before applying its grade.'
            result['recent_completions'].append({
                'attempt_id': row['uuid'], 'module_id': row['module_id'], 'module_title': modules[row['module_id']].title,
                'state': row['state'], 'created_at': recorded_time(row.get('created_at')), 'next_step': next_step,
                'selected_evidence': selected, 'failed_required_outcomes': failed,
            })
        except (CourseCatalogError, TypeError, ValueError):
            result['recent_completions'].append({'state': 'unavailable',
                'next_step': 'An original completion record needs reconciliation; no grade or evidence is inferred.'})
    from .support_operations import support_operations
    result['operations'] = await support_operations(enrollment, package)
    return result
