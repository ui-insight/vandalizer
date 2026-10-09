"""Read-only, aggregate-only inventory. This is never permission to migrate.

Read projected metadata directly, without Beanie initialization/index creation,
learner initialization, model calls or credential preservation side effects.
Two equal reads detect some concurrent changes, not a transactional snapshot.
"""
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
import hashlib

from bson import json_util


class InventoryChanged(ValueError):
    pass


def present(path):
    return {'$not': [{'$in': [{'$ifNull': [path, None]}, [None, False, {}, [], '']]}]}


def fields(*names):
    return dict.fromkeys(('_id', 'user_id', *names), 1)


PROJECTIONS = {
    'progress': {
        **fields('enrollment_id', 'course_version', 'total_xp', 'certified', 'unlocked', 'last_activity_date'),
        'has_position': present('$learning_position'),
        'has_lab': present('$lab_folder_id'),
        'pending_credential': present('$pending_credential'),
        'invalid_modules': {'$ne': [{'$type': '$modules'}, 'object']},
        'modules': {'$map': {
            'input': {'$objectToArray': {'$cond': [{'$eq': [{'$type': '$modules'}, 'object']}, '$modules', {}]}},
            'as': 'module', 'in': {
                'completed': '$$module.v.completed', 'attempts': '$$module.v.attempts',
                'xp_earned': '$$module.v.xp_earned', 'has_answers': present('$$module.v.self_assessment'),
                'invalid': {'$ne': [{'$type': '$$module.v'}, 'object']},
            },
        }},
    },
    'enrollments': fields('uuid', 'progress_id', 'course_version', 'provenance', 'state'),
    'selections': {**fields('active_enrollment_id', 'in_flight_writes'), 'has_write': present('$active_write'),
                   'has_pending_transition': present('$pending_transition_id')},
    'credentials': fields('enrollment_id'),
    'attempts': fields('enrollment_id', 'state'),
    'scenario_attempts': fields('enrollment_id'),
    'lab_inputs': fields('enrollment_id'),
    'lab_executions': fields('enrollment_id', 'state'),
    'review_attempts': fields('enrollment_id', 'state'),
    'learner_decisions': fields('enrollment_id'),
    'process_submissions': fields('enrollment_id'),
    'workflow_design_submissions': fields('enrollment_id'),
    'recoveries': fields('enrollment_id', 'state'),
}


def digest(data):
    return hashlib.sha256(json_util.dumps(data, sort_keys=True).encode()).hexdigest()


def positive(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def classify(metadata):
    """Aggregate projected rows; never return user/record IDs or learner content."""
    groups = defaultdict(lambda: defaultdict(list))
    malformed_owners = Counter()
    for kind in PROJECTIONS:
        for row in metadata.get(kind, []):
            owner = row.get('user_id')
            if not isinstance(owner, str) or not owner:
                malformed_owners[kind] += 1
            else:
                groups[owner][kind].append(row)
    cohorts, flags, versions, activity = Counter(), Counter(), Counter(), Counter()
    activity_dates = []
    for owner, records in groups.items():
        problems, notes = set(), set()
        progress = records['progress']
        enrollments = records['enrollments']
        selections = records['selections']
        enrollment_map = defaultdict(list)
        progress_map = defaultdict(list)
        for row in enrollments:
            enrollment_map[row.get('uuid')].append(row)
        for row in progress:
            if (type(row.get('total_xp', 0)) is not int or row.get('total_xp', 0) < 0
                    or type(row.get('certified', False)) is not bool or type(row.get('unlocked', False)) is not bool):
                problems.add('invalid_progress_values')
            progress_map[str(row.get('_id'))].append(row)
        if len(selections) > 1:
            problems.add('duplicate_selection')
        if any(not key or len(rows) > 1 for key, rows in enrollment_map.items()):
            problems.add('invalid_or_duplicate_enrollment_identity')
        legacy = [row for row in progress if not row.get('enrollment_id')]
        if len(legacy) > 1:
            problems.add('duplicate_legacy_progress')
        if legacy:
            notes.add('unknown_historical_version')
        bound_progress = Counter()
        for enrollment in enrollments:
            matches = progress_map.get(enrollment.get('progress_id'), [])
            bound_progress[enrollment.get('progress_id')] += 1
            if len(matches) != 1:
                problems.add('missing_or_unowned_progress')
                continue
            row = matches[0]
            unknown = enrollment.get('provenance') == 'legacy_version_unknown'
            if unknown:
                notes.add('unknown_historical_version')
            if (row.get('enrollment_id') not in (None, enrollment.get('uuid'))
                    or row.get('course_version') not in (None, enrollment.get('course_version'))
                    or (not unknown and (row.get('enrollment_id') != enrollment.get('uuid')
                                         or row.get('course_version') != enrollment.get('course_version')))):
                problems.add('progress_identity_mismatch')
            if enrollment.get('provenance') not in ('new_enrollment', 'explicit_upgrade', 'legacy_version_unknown'):
                problems.add('unknown_enrollment_provenance')
            if enrollment.get('state') not in ('prepared', 'active', 'completed', 'transferred', 'abandoned'):
                problems.add('unknown_enrollment_state')
            if enrollment.get('state') == 'prepared':
                notes.add('has_prepared_course')
                if (enrollment.get('provenance') != 'explicit_upgrade' or positive(row.get('total_xp')) or row.get('modules')
                        or any(row.get(key) for key in ('certified', 'has_position', 'has_lab', 'pending_credential', 'unlocked'))
                        or any(c.get('enrollment_id') == enrollment.get('uuid') for c in records['credentials'])):
                    problems.add('prepared_course_has_work_or_invalid_provenance')
            if enrollment.get('state') == 'completed' and row.get('certified') is not True:
                problems.add('completion_state_mismatch')
            if row.get('certified') is True and not any(c.get('enrollment_id') == enrollment.get('uuid') for c in records['credentials']):
                notes.add('credential_needs_preservation')
        if any(count > 1 for count in bound_progress.values()):
            problems.add('shared_progress_record')
        for row in progress:
            if row.get('enrollment_id') and (len(enrollment_map.get(row['enrollment_id'], [])) != 1
                                            or str(row['_id']) not in bound_progress):
                problems.add('orphan_versioned_progress')
            if legacy and enrollments and str(row['_id']) not in bound_progress:
                problems.add('unbound_progress_alongside_enrollment')
            if row.get('invalid_modules') or any(m.get('invalid') for m in row.get('modules', [])):
                problems.add('invalid_module_records')
            if row.get('unlocked') is True:
                notes.add('prerequisite_override')
            if row.get('pending_credential'):
                notes.add('pending_credential')
            if any(m.get('has_answers') and m.get('completed') is not True for m in row.get('modules', [])):
                notes.add('unfinished_answers')
            value = row.get('last_activity_date')
            if value:
                try:
                    parsed = date.fromisoformat(value)
                    if parsed.isoformat() != value:
                        raise ValueError
                    activity_dates.append(value)
                    activity['records_with_date'] += 1
                except (ValueError, TypeError):
                    activity['records_with_invalid_date'] += 1
                    problems.add('invalid_activity_date')
            else:
                activity['records_without_date'] += 1
        selected_progress = progress
        if selections:
            selected = enrollment_map.get(selections[0].get('active_enrollment_id'), [])
            if len(selected) != 1:
                problems.add('missing_or_unowned_selection')
            else:
                if (selected[0].get('state') not in ('active', 'completed')
                        and not (selected[0].get('state') == 'prepared' and selections[0].get('has_pending_transition'))):
                    problems.add('selected_read_only_enrollment')
                selected_progress = progress_map.get(selected[0].get('progress_id'), [])
                versions[selected[0].get('course_version') or 'unknown'] += 1
            for selection in selections:
                if selection.get('has_pending_transition'):
                    notes.add('selection_confirmation_pending')
                if selection.get('in_flight_writes') or selection.get('has_write'):
                    notes.add('write_in_flight')
                if bool(selection.get('in_flight_writes')) != bool(selection.get('has_write')):
                    problems.add('write_marker_mismatch')
        elif enrollments:
            problems.add('missing_selection')
        elif progress:
            versions['legacy_unversioned'] += 1
        for kind in PROJECTIONS.keys() - {'progress', 'enrollments', 'selections'}:
            if records[kind]:
                notes.add('saved_' + kind)
            for row in records[kind]:
                if len(enrollment_map.get(row.get('enrollment_id'), [])) != 1:
                    problems.add('orphan_or_unowned_' + kind)
        for kind, pending in {'attempts': {'evaluating', 'graded'}, 'lab_executions': {'executing', 'uncertain'},
                              'review_attempts': {'prepared', 'evaluating', 'unavailable'}, 'recoveries': {'started'}}.items():
            if any(row.get('state') in pending for row in records[kind]):
                notes.add('unresolved_' + kind)
        for kind, states in {'attempts': {'evaluating', 'graded', 'applied', 'rejected', 'failed'},
                             'lab_executions': {'prepared', 'executing', 'completed', 'failed', 'uncertain'},
                             'review_attempts': {'prepared', 'evaluating', 'evaluated', 'unavailable'},
                             'recoveries': {'started', 'completed'}}.items():
            if any(row.get('state') not in states for row in records[kind]):
                problems.add('unknown_' + kind + '_state')
        credential_counts = Counter(row.get('enrollment_id') for row in records['credentials'])
        if any(count > 1 for count in credential_counts.values()):
            problems.add('duplicate_credentials')
        if not progress:
            problems.add('missing_progress')
        if any(row.get('certified') is True for row in progress):
            notes.add('has_completed_history')
            if not enrollments:
                notes.add('credential_needs_preservation')
        completed = any(row.get('certified') is True for row in selected_progress)
        started = any(positive(row.get('total_xp')) or row.get('last_activity_date') or row.get('has_position')
                      or row.get('has_lab') or row.get('pending_credential')
                      or any(m.get('completed') is True or positive(m.get('attempts')) or positive(m.get('xp_earned'))
                             or m.get('has_answers') for m in row.get('modules', [])) for row in selected_progress)
        selected_id = selections[0].get('active_enrollment_id') if len(selections) == 1 else None
        started = started or 'write_in_flight' in notes or any(any(not selected_id or row.get('enrollment_id') == selected_id for row in records[kind])
                                 for kind in PROJECTIONS.keys() - {'progress', 'enrollments', 'selections', 'credentials'})
        cohorts['inconsistent' if problems else 'completed' if completed else 'active' if started else 'unstarted_record'] += 1
        flags.update(problems | notes)
    return {
        'schema_version': 1, 'users_with_certification_records': len(groups),
        'cohorts': {name: cohorts[name] for name in ('unstarted_record', 'active', 'completed', 'inconsistent')},
        'flags_distinct_users': dict(sorted(flags.items())), 'selected_course_counts': dict(sorted(versions.items())),
        'record_counts': {kind: len(metadata.get(kind, [])) for kind in PROJECTIONS},
        'records_with_missing_owner': dict(sorted(malformed_owners.items())),
        'last_activity': {**activity, 'earliest': min(activity_dates, default=None), 'latest': max(activity_dates, default=None)},
        'migration_authorized': False,
        'limits': [
            'Counts cover certification records, not all registered users. Unstarted means no observed activity in those records.',
            'Cohorts describe the selected course; flags include preserved history. Flags overlap and must not be summed.',
            'Overrides mean prerequisite bypass, not proof of a manually awarded credential.',
            'No catalog integrity, credential payload verification, external-job reconciliation or migration safety is established.',
        ],
    }


async def read_metadata(database, *, max_records=100000):
    if max_records < 1:
        raise ValueError('The record limit must be positive')
    result, count = {}, 0
    for kind, projection in PROJECTIONS.items():
        rows = await database['certification_' + ('enrollment_selections' if kind == 'selections' else kind)].aggregate([
            {'$project': projection}, {'$sort': {'_id': 1}}, {'$limit': max_records - count + 1},
        ], maxTimeMS=30000).to_list(None)
        count += len(rows)
        if count > max_records:
            raise ValueError('Inventory record limit exceeded; no partial report is available')
        result[kind] = rows
    return result


async def inventory(database, *, max_records=100000):
    started = datetime.now(timezone.utc).isoformat()
    first = await read_metadata(database, max_records=max_records)
    second = await read_metadata(database, max_records=max_records)
    if digest(first) != digest(second):
        raise InventoryChanged('Certification metadata changed during inspection; rerun the read-only inventory')
    report = classify(second)
    report['metadata_sha256'] = digest(second)
    report['consistency'] = 'equal_metadata_in_two_reads_not_a_transactional_snapshot'
    report['observation_started_at'] = started
    report['observation_finished_at'] = datetime.now(timezone.utc).isoformat()
    return report
