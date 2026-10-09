"""Privacy-safe census of retained course records, not learner analytics.

Aggregate only allowlisted metadata in MongoDB. Do not hydrate answer/receipt
payloads, initialize learners, repair history, or interpret inactivity as dropout.
"""
from datetime import datetime, timezone

from app.models.certification import (
    CertificationAttempt, CertificationEnrollment, CertificationLabExecution,
    CertificationReviewAttempt,
)

MAX_GROUPS = 1000
SOURCES = {
    'enrollments': (CertificationEnrollment, ('prepared', 'active', 'completed', 'transferred', 'abandoned')),
    'module_completions': (CertificationAttempt, ('evaluating', 'graded', 'applied', 'rejected', 'failed')),
    'automatic_reviews': (CertificationReviewAttempt, ('prepared', 'evaluating', 'evaluated', 'unavailable')),
    'lab_runs': (CertificationLabExecution, ('prepared', 'executing', 'completed', 'failed', 'uncertain')),
}
PROVENANCE = ('new_enrollment', 'explicit_upgrade', 'legacy_version_unknown')


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


def pipeline(source):
    _, states = SOURCES[source]
    identity = {
        'course_version': identifier('course_version', r'^[a-z0-9][a-z0-9.-]{0,95}$'),
        'manifest_sha256': identifier('manifest_sha256', r'^[a-f0-9]{64}$'),
        'state': allowed('state', states),
        'provenance': allowed('provenance', PROVENANCE) if source == 'enrollments' else {'$literal': None},
    }
    if source == 'enrollments':
        # The continuation package does not establish the historical course.
        for key in ('course_version', 'manifest_sha256'):
            identity[key] = {'$cond': [{'$eq': ['$provenance', 'legacy_version_unknown']}, None, identity[key]]}
    return [{'$group': {'_id': identity, 'count': {'$sum': 1}}}, {'$limit': MAX_GROUPS + 1}]


async def course_health():
    started = datetime.now(timezone.utc)
    rows = []
    for source, (model, _) in SOURCES.items():
        groups = await model.get_motor_collection().aggregate(
            pipeline(source), maxTimeMS=5000, allowDiskUse=False,
        ).to_list(length=MAX_GROUPS + 1)
        if len(groups) > MAX_GROUPS:
            raise HealthUnavailable('Course health exceeds the bounded report size.')
        rows.extend({'source': source, **group['_id'], 'count': group['count']} for group in groups)
    rows.sort(key=lambda row: tuple(str(row[key] or '') for key in (
        'course_version', 'manifest_sha256', 'source', 'provenance', 'state')))
    return {
        'read_only': True,
        'scope': 'all_retained_records',
        'started_at': started.isoformat(),
        'observed_at': datetime.now(timezone.utc).isoformat(),
        'rows': rows,
        'unavailable_metrics': ['start_failures', 'save_refresh_failures', 'grading_disputes',
                                'abandonment_rate', 'resume_success', 'bridge_uptake'],
    }
