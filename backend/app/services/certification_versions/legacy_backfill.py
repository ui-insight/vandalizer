"""Restartable backfill of unversioned progress into explicit legacy enrollments.

The dry run only reads. Apply runs only the exact plan an operator reviewed and
uses `ensure_initial`: deterministic IDs, insert-only enrollment/selection
writes and no write to the legacy progress record. Credit, stars, XP, dates,
reflections and lab references therefore stay in place, and the before/after
reconciliation proves it per user. Nothing is reset, merged or relabeled.

Historical version (C8-MIGRATE-02): only a versioned enrollment whose pinned
manifest matches the catalog identifies a course version. No legacy field does.
Dates, XP, module titles, completion and stray version strings are not version
evidence, so every legacy record becomes `legacy_version_unknown` (reported as
`legacy_unversioned`). A stray version hint blocks backfill for reconciliation
rather than being trusted or discarded.
"""
from collections.abc import Mapping, Sequence
from motor.motor_asyncio import AsyncIOMotorDatabase
from .catalog import CourseCatalog, CoursePackage
from .enrollments import EnrollmentRepository
from collections import Counter
from datetime import datetime, timezone
import hashlib
from types import SimpleNamespace

from bson import json_util

from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict, initial_enrollment_id
from .reward_ledger import enrollment_rewards

COLLECTIONS = {'progress': 'certification_progress', 'enrollments': 'certification_enrollments',
               'selections': 'certification_enrollment_selections'}
VERSION_POLICY = ('No legacy record identifies the course content a learner saw. Dates, XP, module titles, '
                  'completion and stray version strings are not version evidence; legacy history is labeled '
                  'legacy_unversioned and never relabeled as 4.0 or 5.0 competence.')


class BackfillChanged(ValueError):
    pass


def digest(value: object) -> str:
    return hashlib.sha256(json_util.dumps(value, sort_keys=True).encode()).hexdigest()


def user_key(user_id: str) -> str:
    """Stable pseudonymous key; reports never print account identifiers."""
    return hashlib.sha256(('vandalizer:certification:backfill:' + user_id).encode()).hexdigest()[:16]


def _count(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def summarize(raw: dict, package: CoursePackage | None=None) -> dict:
    modules = raw.get('modules')
    if not isinstance(modules, dict):
        modules = {}
    rows = {key: value for key, value in modules.items() if isinstance(value, dict)}
    completed = sorted(key for key, value in rows.items() if value.get('completed') is True)
    dates = sorted(str(rows[key]['completed_at']) for key in completed if rows[key].get('completed_at'))
    answers = [value['self_assessment'] for value in rows.values() if isinstance(value.get('self_assessment'), dict) and value['self_assessment']]
    certified_at = raw.get('certified_at')
    summary = {
        'progress_sha256': digest(raw), 'completed_modules': completed,
        'stars': sum(_count(rows[key].get('stars')) for key in completed),
        'total_xp': raw.get('total_xp'), 'module_xp': sum(_count(value.get('xp_earned')) for value in rows.values()),
        'completion_dates': len(dates), 'earliest_completion': dates[0] if dates else None,
        'latest_completion': dates[-1] if dates else None,
        'certified': raw.get('certified') is True,
        'certified_at': certified_at.isoformat() if isinstance(certified_at, datetime) else certified_at,
        'last_activity_date': raw.get('last_activity_date'),
        'reflections': len(answers), 'reflection_answers': sum(len(item) for item in answers),
        'lab_folder': bool(raw.get('lab_folder_id')),
        'provisioned_docs': sum(len(value['provisioned_docs']) for value in rows.values() if isinstance(value.get('provisioned_docs'), list)),
        'learning_position': bool(raw.get('learning_position')),
        'historical_version': 'legacy_unversioned',
    }
    if package is not None and isinstance(raw.get('total_xp'), int):
        ledger = enrollment_rewards(package, SimpleNamespace(enrollment_id=None, modules=rows, total_xp=raw['total_xp']),
                                    provenance='legacy_version_unknown')
        summary.update(xp_explained=ledger['explained'], unexplained_xp=ledger['unexplained_xp'])
    return summary


def classify(user_id: str, progress: Sequence[dict], enrollments: Sequence[dict], selections: Sequence[dict]) -> tuple[str, list[str]]:
    legacy = [row for row in progress if not row.get('enrollment_id')]
    reasons = set()
    if len(legacy) > 1:
        reasons.add('duplicate_legacy_progress')
    record = legacy[0]
    if record.get('course_version') is not None:
        reasons.add('unverified_version_hint')
    if not isinstance(record.get('modules', {}), dict) or any(not isinstance(v, dict) for v in (record.get('modules') or {}).values()):
        reasons.add('invalid_module_records')
    if type(record.get('total_xp', 0)) is not int or record.get('total_xp', 0) < 0 or type(record.get('certified', False)) is not bool:
        reasons.add('invalid_progress_values')
    if len(selections) > 1:
        reasons.add('duplicate_selection')
    if any(row.get('in_flight_writes') or row.get('active_write') for row in selections):
        reasons.add('write_in_flight')
    bound = [row for row in enrollments if row.get('progress_id') == str(record['_id'])]
    status = 'ready'
    if bound:
        if (len(bound) != 1 or bound[0].get('uuid') != initial_enrollment_id(user_id)
                or bound[0].get('provenance') != 'legacy_version_unknown'):
            reasons.add('legacy_progress_bound_to_other_enrollment')
        elif selections:
            status = 'already_backfilled'
        else:
            status = 'resume'
    elif enrollments:
        reasons.add('unbound_legacy_progress_alongside_enrollments')
    elif selections:
        reasons.add('selection_without_enrollment')
    return ('needs_reconciliation' if reasons else status), sorted(reasons)


async def read_records(database: AsyncIOMotorDatabase, *, max_records: int=100000) -> dict[str, list[dict]]:
    result, count = {}, 0
    for kind, name in COLLECTIONS.items():
        rows = await database[name].find({}).sort('_id', 1).limit(max_records - count + 1).to_list(None)
        count += len(rows)
        if count > max_records:
            raise ValueError('Backfill record limit exceeded; no partial plan is available')
        result[kind] = rows
    return result


def build_plan(records: Mapping[str, list[dict]], catalog: CourseCatalog) -> tuple[dict, dict[str, str]]:
    registry = catalog.registry()
    continuation = registry.get('legacy_continuation')
    blockers, package = [], None
    if not continuation:
        blockers.append('legacy_continuation_not_configured')
    else:
        try:
            package = catalog.load(continuation)
        except CourseCatalogError:
            blockers.append('legacy_continuation_not_supported')
    owners: Counter[str] = Counter()
    grouped: dict[str, dict[str, list[dict]]] = {}
    for kind, rows in records.items():
        for row in rows:
            owner = row.get('user_id')
            if not isinstance(owner, str) or not owner:
                owners[kind] += 1
                continue
            grouped.setdefault(owner, {key: [] for key in COLLECTIONS})[kind].append(row)
    users: list[dict] = []
    internal: dict[str, str] = {}
    known: Counter[str] = Counter()
    for owner, user_records in sorted(grouped.items(), key=lambda item: user_key(item[0])):
        for row in user_records['enrollments']:
            if row.get('provenance') in ('new_enrollment', 'explicit_upgrade'):
                try:
                    verified = catalog.load(row['course_version'], preview=True).manifest_sha256 == row.get('manifest_sha256')
                except (CourseCatalogError, KeyError, ValueError):
                    verified = False
                known[row['course_version'] if verified else 'unverifiable_versioned_record'] += 1
        if not any(not row.get('enrollment_id') for row in user_records['progress']):
            continue
        status, reasons = classify(owner, user_records['progress'], user_records['enrollments'], user_records['selections'])
        legacy = next(row for row in user_records['progress'] if not row.get('enrollment_id'))
        key = user_key(owner)
        internal[key] = owner
        users.append({'user_key': key, 'status': status, 'reasons': reasons, 'summary': summarize(legacy, package)})
    totals: Counter[str] = Counter()
    for row in users:
        item = row['summary']
        totals.update(users=1, completed_modules=len(item['completed_modules']), stars=item['stars'],
                      total_xp=_count(item['total_xp']), module_xp=item['module_xp'], completion_dates=item['completion_dates'],
                      certified=item['certified'], reflections=item['reflections'], reflection_answers=item['reflection_answers'],
                      lab_folders=item['lab_folder'], provisioned_docs=item['provisioned_docs'],
                      xp_unexplained_users=item.get('xp_explained') is False)
    plan = {'schema_version': 1, 'kind': 'legacy_enrollment_backfill_plan', 'legacy_continuation': continuation,
            'can_apply': not blockers, 'blockers': blockers,
            'record_counts': {kind: len(rows) for kind, rows in records.items()},
            'records_with_missing_owner': dict(sorted(owners.items())),
            'statuses': dict(sorted(Counter(row['status'] for row in users).items())),
            'reasons_distinct_users': dict(sorted(Counter(r for row in users for r in row['reasons']).items())),
            'totals': dict(sorted(totals.items())), 'known_versions': dict(sorted(known.items())),
            'historical_version_policy': VERSION_POLICY, 'users': users,
            'limits': ['Needs-reconciliation users are never backfilled automatically; resolve each record explicitly first.',
                       'Credential preservation for certified legacy learners is the separate preserve_legacy step.',
                       'Two equal reads detect some concurrent changes; they are not a transactional snapshot.']}
    plan['plan_sha256'] = digest(plan)
    return plan, internal


async def dry_run(database: AsyncIOMotorDatabase, catalog: CourseCatalog, *, max_records: int=100000) -> dict:
    first = await read_records(database, max_records=max_records)
    second = await read_records(database, max_records=max_records)
    if digest(first) != digest(second):
        raise BackfillChanged('Certification records changed during the dry run; run it again')
    plan, _ = build_plan(second, catalog)
    return {**plan, 'dry_run': True, 'observed_at': datetime.now(timezone.utc).isoformat()}


async def apply(repository: EnrollmentRepository, database: AsyncIOMotorDatabase, *, expected_plan_sha256: str, max_records: int=100000) -> dict:
    """Backfill the reviewed plan's ready/resume users, then reconcile before/after."""
    before, internal = build_plan(await read_records(database, max_records=max_records), repository.catalog)
    if before['plan_sha256'] != expected_plan_sha256:
        raise BackfillChanged('Records or catalog changed since the reviewed dry run; review a new dry run')
    if not before['can_apply']:
        raise CourseCatalogError('Configure a supported legacy continuation course before backfilling')
    outcomes: dict[str, str | None] = {}
    for row in before['users']:
        if row['status'] not in ('ready', 'resume'):
            continue
        try:
            await repository.ensure_initial(internal[row['user_key']])
            outcomes[row['user_key']] = None
        except (EnrollmentConflict, CourseCatalogError) as exc:
            outcomes[row['user_key']] = str(exc)
    after, _ = build_plan(await read_records(database, max_records=max_records), repository.catalog)
    after_users = {row['user_key']: row for row in after['users']}
    users = []
    for row in before['users']:
        later = after_users.get(row['user_key'])
        unchanged = later is not None and later['summary'] == row['summary']
        entry = {'user_key': row['user_key'], 'status_before': row['status'],
                 'status_after': later['status'] if later else 'missing', 'progress_unchanged': unchanged}
        if row['user_key'] in outcomes:
            entry['error'] = outcomes[row['user_key']]
        users.append(entry)
    backfilled = [row for row in users if 'error' in row and row['error'] is None]
    expected = {'progress': before['record_counts']['progress'],
                'enrollments': before['record_counts']['enrollments'] + sum(row['status_before'] == 'ready' for row in backfilled),
                'selections': before['record_counts']['selections'] + len(backfilled)}
    reconciled = (after['totals'] == before['totals'] and after['record_counts'] == expected
                  and all(row['progress_unchanged'] for row in users)
                  and all(row['status_after'] == 'already_backfilled' for row in backfilled))
    return {'schema_version': 1, 'kind': 'legacy_enrollment_backfill_result',
            'before_plan_sha256': before['plan_sha256'], 'after_plan_sha256': after['plan_sha256'],
            'backfilled_users': len(backfilled), 'failed_users': sum(1 for row in users if row.get('error')),
            'record_counts': {'before': before['record_counts'], 'after': after['record_counts'], 'expected_after': expected},
            'totals_before': before['totals'], 'totals_after': after['totals'],
            'statuses_after': after['statuses'], 'users': users, 'reconciled': reconciled}
