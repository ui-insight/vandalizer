"""Explainable XP and credentials per enrollment; read-only, never repairs totals.

Reward rule (C8-MIGRATE-09):
- Base XP is earned once, in the enrollment whose assessment first earned the
  module. A transferred module adds `xp_carried` to the target course's progress
  total but earns no base XP there; the reward stays with the original.
- Stars and their bonus belong to the course that assessed them. Legacy stars
  stay in the legacy course; 5.0 has one completion threshold and no star bonus,
  so they never convert into 5.0 stars or XP.
- Work completed in a bridge or upgraded course earns that course's base XP once.
  A later reassessment of carried credit earns only a genuinely new star bonus.
- A credential belongs to one enrollment and is issued at most once for it.
Lifetime earned XP sums earned XP only; carried XP is shown, never added twice.
Recorded totals that the rule cannot explain are reported, not rewritten.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.certification import CertificationProgress
    from app.services.certification_versions.catalog import CoursePackage



def _module(item, saved, star_bonus, legacy) -> dict:
    if not isinstance(saved, dict):
        saved = {}
    completed = saved.get('completed') is True
    carried = saved.get('xp_carried', 0) if isinstance(saved.get('xp_carried'), int) else 0
    earned = saved.get('xp_earned', 0) if isinstance(saved.get('xp_earned'), int) else 0
    stars = saved.get('stars', 0) if isinstance(saved.get('stars'), int) else 0
    base = item.base_xp if completed and not carried else 0
    star_xp = earned - base
    origin = (saved.get('credit_origin') or ('legacy_module_credit' if legacy else 'assessed')) if completed else None
    # Carried credit includes its own completion threshold; only later stars can earn a bonus.
    expected_star_xp = max(stars - (1 if carried else 0), 0) * star_bonus if completed else 0
    return {'module_id': item.id, 'completed': completed, 'credit_origin': origin, 'stars': stars,
            'base_xp_earned': base, 'star_bonus_xp': star_xp, 'xp_carried': carried, 'xp_earned': earned,
            'explained': star_xp == expected_star_xp and (completed or earned == 0)}


def enrollment_rewards(package: CoursePackage, progress: CertificationProgress, *, provenance=None, credential_id=None) -> dict:
    legacy = provenance == 'legacy_version_unknown'
    modules = [_module(item, progress.modules.get(item.id), package.manifest.star_bonus_xp, legacy)
               for item in package.manifest.modules]
    earned = sum(row['xp_earned'] for row in modules)
    carried = sum(row['xp_carried'] for row in modules)
    unexplained = progress.total_xp - earned - carried
    return {'enrollment_id': progress.enrollment_id, 'course_version': package.manifest.release_id,
            'provenance': provenance, 'modules': modules,
            'stars': sum(row['stars'] for row in modules if row['completed']),
            'base_xp_earned': sum(row['base_xp_earned'] for row in modules),
            'star_bonus_xp': sum(row['star_bonus_xp'] for row in modules),
            'earned_xp': earned, 'carried_xp': carried, 'recorded_total_xp': progress.total_xp,
            'unexplained_xp': unexplained,
            'explained': unexplained == 0 and all(row['explained'] for row in modules),
            'credential_id': credential_id}


def user_rewards(rows) -> dict:
    """Combine per-enrollment ledgers; carried XP never enters the lifetime total."""
    credentials = [row['credential_id'] for row in rows if row['credential_id']]
    return {'enrollments': rows, 'lifetime_earned_xp': sum(row['earned_xp'] for row in rows),
            'carried_xp_shown_in_target_courses': sum(row['carried_xp'] for row in rows),
            'credentials': credentials, 'duplicate_credentials': len(credentials) != len(set(credentials)),
            'explained': all(row['explained'] for row in rows) and len(credentials) == len(set(credentials)),
            'explanation': [
                'Each course keeps the XP and stars its own assessments earned.',
                'Carried XP counts toward the selected course’s progress but is not a second reward; lifetime XP counts it once, where it was earned.',
                'Legacy stars stay with the legacy course. The 5.0 course has a single completion threshold and no star bonus.',
                'Each earned credential belongs to one course enrollment; an earlier credential is never reissued or relabeled.',
            ]}


async def load_user_rewards(repository, user_id: str):
    from .credentials import CredentialRepository
    credentials = CredentialRepository()
    rows = []
    for raw in await repository.enrollments.find({'user_id': user_id}).sort('created_at', 1).to_list(None):
        progress = await repository.read_progress(user_id, raw['uuid'])
        credential = await credentials.for_enrollment(user_id, raw['uuid'])
        rows.append(enrollment_rewards(repository.catalog.load(raw['course_version']), progress,
                                       provenance=raw['provenance'],
                                       credential_id=credential.credential_id if credential else None))
    return user_rewards(rows)
