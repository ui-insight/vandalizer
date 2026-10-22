"""Privacy-safe census of retained course records, not learner analytics.

Aggregate only allowlisted metadata in MongoDB. Do not hydrate answer/receipt
payloads, initialize learners, repair history, or interpret inactivity as dropout.

Inactivity: an active enrollment whose latest server-recorded activity (course
start, saved reading place, legacy activity date or module completion request)
is older than INACTIVE_AFTER_DAYS. Sixty days is twice the journey window and
spans a proposal-deadline or month-end pause in self-paced professional study,
so one quiet month is not counted. It is reported as inactive, never as
dropout: the records cannot say why someone stopped or whether they will return.
"""
from datetime import datetime, timedelta, timezone

from app.models.certification import (
    CertificationAttempt, CertificationEnrollment, CertificationLabExecution,
    CertificationProgress, CertificationReviewAttempt,
)
from app.models.certification_journey import CertificationJourneyEvent
from .catalog import CourseCatalog, CourseCatalogError
from .journey_events import EVENTS

MAX_GROUPS = 1000
SOURCES = {
    'enrollments': (CertificationEnrollment, ('prepared', 'active', 'completed', 'transferred', 'abandoned')),
    'module_completions': (CertificationAttempt, ('evaluating', 'graded', 'applied', 'rejected', 'failed')),
    'automatic_reviews': (CertificationReviewAttempt, ('prepared', 'evaluating', 'evaluated', 'unavailable')),
    'lab_runs': (CertificationLabExecution, ('prepared', 'executing', 'completed', 'failed', 'uncertain')),
}
PROVENANCE = ('new_enrollment', 'explicit_upgrade', 'legacy_version_unknown')
VERSION_PATTERN = r'^[a-z0-9][a-z0-9.-]{0,95}$'
MANIFEST_PATTERN = r'^[a-f0-9]{64}$'
JOURNEY_WINDOW_DAYS = 30
INACTIVE_AFTER_DAYS = 60
# Rates over fewer records are withheld: they swing on one person and can
# point at an individual in a small cohort.
MIN_RATE_DENOMINATOR = 5
# Prepared enrollments are not starts.
STARTED = ('active', 'completed', 'transferred', 'abandoned')
JOURNEY_FIELDS = {'grading_question_opened': 'grading_questions_opened',
                  'saved_lesson_displayed': 'resumes_restored',
                  'saved_lesson_unavailable': 'resumes_unavailable'}


class HealthUnavailable(ValueError):
    pass


def allowed(field, values):
    return {'$cond': [{'$in': [f'${field}', list(values)]}, f'${field}', 'unknown']}


def identifier(field, pattern):
    return {'$cond': [
        {'$regexMatch': {'input': {'$cond': [{'$eq': [{'$type': f'${field}'}, 'string']}, f'${field}', '']},
                         'regex': pattern}},
        f'${field}', None,
    ]}


def course_identity(*, legacy_unknown=False):
    identity = {'course_version': identifier('course_version', VERSION_PATTERN),
                'manifest_sha256': identifier('manifest_sha256', MANIFEST_PATTERN)}
    if legacy_unknown:
        # The continuation package does not establish the historical course.
        for key in identity:
            identity[key] = {'$cond': [{'$eq': ['$provenance', 'legacy_version_unknown']}, None, identity[key]]}
    return identity


def pipeline(source):
    _, states = SOURCES[source]
    identity = {
        **course_identity(legacy_unknown=source == 'enrollments'),
        'state': allowed('state', states),
        'provenance': allowed('provenance', PROVENANCE) if source == 'enrollments' else {'$literal': None},
    }
    return [{'$group': {'_id': identity, 'count': {'$sum': 1}}}, {'$limit': MAX_GROUPS + 1}]


def as_date(expression):
    return {'$convert': {'input': expression, 'to': 'date', 'onError': None, 'onNull': None}}


def count_if(condition):
    return {'$sum': {'$cond': [condition, 1, 0]}}


def enrollment_outcomes_pipeline(cutoff):
    """Started enrollments by course, using only activity timestamps."""
    active = {'$eq': ['$state', 'active']}
    return [
        {'$match': {'state': {'$in': list(STARTED)}}},
        {'$lookup': {
            'from': CertificationProgress.get_collection_name(),
            'let': {'progress': {'$convert': {'input': '$progress_id', 'to': 'objectId', 'onError': None, 'onNull': None}}},
            'pipeline': [{'$match': {'$expr': {'$eq': ['$_id', '$$progress']}}},
                         {'$project': {'_id': 0, 'saved_at': '$learning_position.saved_at', 'last_activity_date': 1}}],
            'as': 'progress'}},
        {'$lookup': {
            'from': CertificationAttempt.get_collection_name(),
            'let': {'enrollment': '$uuid', 'user': '$user_id'},
            'pipeline': [{'$match': {'$expr': {'$and': [{'$eq': ['$user_id', '$$user']},
                                                        {'$eq': ['$enrollment_id', '$$enrollment']}]}}},
                         {'$group': {'_id': None, 'latest': {'$max': '$created_at'}}}],
            'as': 'attempts'}},
        {'$project': {'_id': 0, 'state': 1, 'provenance': 1, 'course_version': 1, 'manifest_sha256': 1,
                      'last_activity': {'$max': [
                          as_date('$created_at'),
                          as_date({'$arrayElemAt': ['$progress.saved_at', 0]}),
                          as_date({'$arrayElemAt': ['$progress.last_activity_date', 0]}),
                          as_date({'$arrayElemAt': ['$attempts.latest', 0]}),
                      ]}}},
        {'$group': {
            '_id': course_identity(legacy_unknown=True),
            'started': {'$sum': 1},
            'active': count_if(active),
            'completed': count_if({'$eq': ['$state', 'completed']}),
            'transferred': count_if({'$eq': ['$state', 'transferred']}),
            'inactive': count_if({'$and': [active, {'$ne': ['$last_activity', None]}, {'$lt': ['$last_activity', cutoff]}]}),
            'activity_unknown': count_if({'$and': [active, {'$eq': ['$last_activity', None]}]}),
        }},
        {'$limit': MAX_GROUPS + 1},
    ]


def bridge_pipeline():
    """Learners with a historical course record who explicitly started a newer course."""
    return [
        {'$group': {
            '_id': '$user_id',
            'legacy': {'$max': {'$cond': [{'$eq': ['$provenance', 'legacy_version_unknown']}, 1, 0]}},
            'targets': {'$addToSet': {'$cond': [
                {'$and': [{'$eq': ['$provenance', 'explicit_upgrade']}, {'$in': ['$state', list(STARTED)]}]},
                course_identity(), '$$REMOVE']}},
        }},
        {'$match': {'legacy': 1}},
        {'$facet': {
            'totals': [{'$group': {'_id': None, 'legacy_learners': {'$sum': 1},
                                   'upgraded_learners': count_if({'$gt': [{'$size': '$targets'}, 0]})}}],
            'targets': [{'$unwind': '$targets'}, {'$group': {'_id': '$targets', 'learners': {'$sum': 1}}},
                        {'$limit': MAX_GROUPS + 1}],
        }},
    ]


def rate(numerator, denominator):
    return round(numerator / denominator, 4) if denominator >= MIN_RATE_DENOMINATOR else None


async def aggregate(model, stages, message):
    groups = await model.get_motor_collection().aggregate(
        stages, maxTimeMS=5000, allowDiskUse=False).to_list(length=MAX_GROUPS + 1)
    if len(groups) > MAX_GROUPS:
        raise HealthUnavailable(message)
    return groups


def course_key(row):
    return row.get('course_version'), row.get('manifest_sha256')


def sort_key(row):
    return tuple(str(value or '') for value in course_key(row))


def course_titles(keys):
    """Plain-language titles for the exact registered packages; unknown stays None."""
    titles, catalog = {}, CourseCatalog()
    for version, manifest in keys:
        if not version or not manifest:
            continue
        try:
            package = catalog.load(version, preview=True)
        except CourseCatalogError:
            continue
        if package.manifest_sha256 == manifest:
            titles[(version, manifest)] = package.manifest.title
    return titles


async def journey_success(started, journey_start, journey_rows):
    courses = {}

    def course(identity):
        return courses.setdefault(course_key(identity), {
            'course_version': identity.get('course_version'), 'manifest_sha256': identity.get('manifest_sha256'),
            'started': 0, 'active': 0, 'completed': 0, 'transferred': 0, 'inactive': 0, 'activity_unknown': 0,
            'staff_grading_corrections': 0, 'grading_questions_opened': 0,
            'resumes_restored': 0, 'resumes_unavailable': 0,
        })

    cutoff = started - timedelta(days=INACTIVE_AFTER_DAYS)
    for group in await aggregate(CertificationEnrollment, enrollment_outcomes_pipeline(cutoff),
                                 'Enrollment outcomes exceed the bounded report size.'):
        course(group['_id']).update({name: group[name] for name in (
            'started', 'active', 'completed', 'transferred', 'inactive', 'activity_unknown')})
    # A linked regrade exists only after an administrator reviewed a grading concern.
    for group in await aggregate(CertificationReviewAttempt, [
        {'$match': {'parent_attempt_id': {'$type': 'string'}}},
        {'$group': {'_id': course_identity(), 'count': {'$sum': 1}}}, {'$limit': MAX_GROUPS + 1},
    ], 'Grading corrections exceed the bounded report size.'):
        course(group['_id'])['staff_grading_corrections'] = group['count']
    for row in journey_rows:
        if row['state'] in JOURNEY_FIELDS:
            course(row)[JOURNEY_FIELDS[row['state']]] += row['count']
    for row in courses.values():
        row.update(
            # Transferred enrollments continue in another course.
            completion_rate=rate(row['completed'], row['started'] - row['transferred']),
            inactive_share=rate(row['inactive'], row['active']),
            resume_success_rate=rate(row['resumes_restored'], row['resumes_restored'] + row['resumes_unavailable']),
        )
    bridge = (await aggregate(CertificationEnrollment, bridge_pipeline(), 'Bridge uptake exceeds the bounded report size.'))[0]
    if len(bridge['targets']) > MAX_GROUPS:
        raise HealthUnavailable('Bridge uptake exceeds the bounded report size.')
    totals = (bridge['totals'] or [{'legacy_learners': 0, 'upgraded_learners': 0}])[0]
    targets = sorted(({**group['_id'], 'learners': group['learners']} for group in bridge['targets']), key=sort_key)
    rows = sorted(courses.values(), key=sort_key)
    titles = course_titles({course_key(row) for row in [*rows, *targets]})
    for row in [*rows, *targets]:
        row['course_title'] = titles.get(course_key(row))
    return {
        'inactive_after_days': INACTIVE_AFTER_DAYS,
        'min_rate_denominator': MIN_RATE_DENOMINATOR,
        'journey_window_days': JOURNEY_WINDOW_DAYS,
        'courses': rows,
        'bridge': {'legacy_learners': totals['legacy_learners'], 'upgraded_learners': totals['upgraded_learners'],
                   'uptake_rate': rate(totals['upgraded_learners'], totals['legacy_learners']), 'targets': targets},
    }


async def course_health():
    started = datetime.now(timezone.utc)
    rows = []
    for source, (model, _) in SOURCES.items():
        groups = await aggregate(model, pipeline(source), 'Course health exceeds the bounded report size.')
        rows.extend({'source': source, **group['_id'], 'count': group['count']} for group in groups)
    rows.sort(key=lambda row: tuple(str(row[key] or '') for key in (
        'course_version', 'manifest_sha256', 'source', 'provenance', 'state')))
    journey_start = started - timedelta(days=JOURNEY_WINDOW_DAYS)
    groups = await aggregate(CertificationJourneyEvent, [
        {'$match': {'observed_at': {'$gte': journey_start, '$lte': started}}},
        {'$group': {'_id': {**course_identity(), 'state': allowed('state', EVENTS)}, 'count': {'$sum': 1}}},
        {'$limit': MAX_GROUPS + 1},
    ], 'Journey observations exceed the bounded report size.')
    journey_rows = sorted([{'source': 'client_journey', 'provenance': None, **group['_id'], 'count': group['count']}
                           for group in groups], key=lambda row: tuple(str(row[key] or '') for key in ('course_version', 'manifest_sha256', 'state')))
    return {
        'read_only': True,
        'scope': 'all_retained_records',
        'started_at': started.isoformat(),
        'observed_at': datetime.now(timezone.utc).isoformat(),
        'rows': rows,
        'journey': {'window_days': JOURNEY_WINDOW_DAYS, 'window_started_at': journey_start.isoformat(),
                    'window_ended_at': started.isoformat(), 'source': 'client_observation', 'rows': journey_rows},
        'journey_success': await journey_success(started, journey_start, journey_rows),
        # Inactivity is measured; why someone stopped is not. A grading question
        # opened from a result is counted, but whether support upheld it is not linked.
        'unavailable_metrics': ['dropout', 'grading_question_outcomes'],
        **release_status(rows),
    }


def release_status(rows):
    """This worker's release fingerprint and any enrolled course it cannot serve.

    Each refresh may reach a different worker; differing fingerprints mean the
    deployment is serving mixed releases. Diagnoses read packages, not learners.
    """
    from .catalog import CourseCatalog, CourseCatalogError
    from .release_coherence import deployment_identity, diagnose_release
    catalog = CourseCatalog()
    try:
        identity = deployment_identity(catalog)
    except (CourseCatalogError, OSError):
        identity = {'status': 'unavailable', 'explanation': 'This worker cannot read a valid course registry.'}
    versions = sorted({row['course_version'] for row in rows
                       if row['source'] == 'enrollments' and row['course_version']})
    incidents = [diagnosis for diagnosis in (diagnose_release(catalog, version) for version in versions)
                 if diagnosis['status'] != 'available']
    return {'release_identity': identity, 'release_incidents': incidents}
