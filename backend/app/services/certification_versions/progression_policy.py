"""Pinned draft progression rules, separate from release verification."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProgressionPolicy(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    schema_version: Literal[1] = 1
    policy_id: Literal['required-outcomes-flexible-order.1']
    state: Literal['design_draft', 'release_candidate']
    module_order: tuple[str, ...]
    module_xp: dict[str, int] = Field(min_length=1)
    learning_order: Literal['any_order']
    credential_requirement: Literal['all_required_outcomes_in_all_modules']
    credit: Literal['base_xp_once_per_module']
    maximum_stars: Literal[1]
    star_bonus_xp: Literal[0]
    enrichment_awards_credit: Literal[False]
    retry_rule: Literal['new_evidence_new_attempt_replay_original_request']
    critical_errors: Literal['revision_required_no_credit']
    technical_failures: Literal['retry_original_grading_without_learner_failure']
    grading_mode: Literal['automatic_only']
    staff_queue_enabled: Literal[False]
    time_limit_seconds: None
    speed_affects_grade: Literal[False]
    accessibility: Literal['equivalent_criteria_unassessed_presentation_changes']
    levels_policy: Literal['xp_milestones_not_credentials']
    legacy_credit: Literal['preserve_original_no_automatic_transfer']

    @model_validator(mode='after')
    def coverage(self):
        if (not self.module_order or len(set(self.module_order)) != len(self.module_order)
                or set(self.module_order) != set(self.module_xp)
                or any(type(value) is not int or value <= 0 for value in self.module_xp.values())):
            raise ValueError('Progression policy requires distinct modules and positive base XP')
        return self


def package_progression_policy(package):
    """Old immutable packages retain their original requirements without backfill."""
    if 'progression-policy.json' not in package.manifest.artifacts:
        return None
    from .outcomes import package_outcomes
    policy = ProgressionPolicy.model_validate_json(package.read('progression-policy.json'))
    contract = package_outcomes(package)
    manifest = package.manifest
    if (contract is None or tuple(module.id for module in manifest.modules) != policy.module_order
            or {module.id: module.base_xp for module in manifest.modules} != policy.module_xp
            or any(module.prerequisites for module in manifest.modules)
            or manifest.maximum_stars != policy.maximum_stars or manifest.star_bonus_xp != policy.star_bonus_xp):
        raise ValueError('Course requirements differ from their pinned progression policy')
    if package.entry.state != 'draft' and policy.state != 'release_candidate':
        raise ValueError('Published progression policy must be a reviewed release candidate')
    structure = package.json('course-structure.json')
    levels = structure['levels']
    thresholds = [level['xp'] for level in levels]
    if (not levels or len({level['name'] for level in levels}) != len(levels)
            or any(type(value) is not int or value < 0 for value in thresholds)
            or thresholds[0] != 0 or thresholds != sorted(set(thresholds))
            or thresholds[-1] > sum(policy.module_xp.values())):
        raise ValueError('Progression milestones must be ordered and reachable without bonus credit')
    tier_modules = [module for tier in structure['tiers'] for module in tier['moduleIds']]
    if len(tier_modules) != len(policy.module_order) or set(tier_modules) != set(policy.module_order):
        raise ValueError('Journey groups must cover each required module exactly once')
    return policy


def public_progression_policy(package):
    policy = package_progression_policy(package)
    if policy is None:
        return None
    from .outcomes import package_outcomes
    contract = package_outcomes(package)
    return {'policy_id': policy.policy_id, 'state': policy.state,
        'required_modules': len(policy.module_order), 'required_outcomes': len(contract.required_outcomes()),
        'base_xp_total': sum(policy.module_xp.values()),
        'rules': [
            'Study modules in any order. The course order is a suggested learning path, not a prerequisite lock.',
            'Complete every required outcome in every module to earn this course’s certificate. Reading, practice and reflections do not earn assessed credit.',
            'Required scope, authorization, source-checking and recovery errors need correction before credit. Stronger work elsewhere cannot compensate for a failed required outcome.',
            'A completed module earns its base XP once. There is one completion threshold, no bonus stars and no credit for optional enrichment. XP levels are milestones, not additional credentials.',
            'Use your saved feedback to revise insufficient evidence, then submit the new evidence for another assessment. Reopening a saved result does not repeat the assessment or award more XP.',
            'Technical grading failures can be retried without counting as learner failures. Assessment is automatic, with feedback to guide your next revision.',
            'There is no course assessment timer, and speed does not affect the grade. You may pause and resume, enlarge text, use keyboard controls or change the learning panel position without approval or a grade penalty. These presentation choices do not change the required evidence.',
            'Use the supported alternative stated in the assignment when an optional integration or restricted operation is unavailable. External secrets, administrator enablement and staff grading are not course requirements.',
            'If you cannot access a required source or assessment control, preserve your saved work and stop that assessment until access is restored. Do not replace missing evidence with a claim of completion. Technical recovery and presentation changes cannot waive an assessed outcome.',
        ]}
