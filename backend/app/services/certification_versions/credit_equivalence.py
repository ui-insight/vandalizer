"""Read-only, explicitly authored equivalence; never applies credit or XP.

Rules are immutable target-package assets, not request parameters. A compatible
rubric alone is insufficient: original, enrollment-bound assessed credit must
also validate. Legacy participation remains earned in its original course.
"""
from typing import Literal

from pydantic import Field, model_validator

from .attempts import encode
from .catalog import CourseCatalogError
from .outcome_credit import verified_credit_snapshot
from .outcomes import ContractModel, package_outcomes


class EquivalenceRule(ContractModel):
    rule_id: str = Field(min_length=1)
    outcome_id: str
    reason: str = Field(min_length=20)


class EquivalencePolicy(ContractModel):
    schema_version: Literal[1] = 1
    policy_id: str = Field(min_length=1)
    source_version: str
    source_manifest_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    target_version: str
    assessment_basis_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    rules: tuple[EquivalenceRule, ...] = Field(min_length=1)

    @model_validator(mode='after')
    def unique_rules(self):
        if (len({rule.rule_id for rule in self.rules}) != len(self.rules)
                or len({rule.outcome_id for rule in self.rules}) != len(self.rules)):
            raise ValueError('Equivalence rules and target outcomes must be unique')
        return self


def assessment_basis(package):
    """Conservative compatibility boundary; only presentation may differ.

Unknown assets are included by default. New exercises, judge configuration,
runtime code, source documents or progression rules invalidate the mapping.
The mapping itself is excluded to avoid a circular package digest.
"""
    contract = package_outcomes(package)
    if contract is None:
        return None
    definition = contract.model_dump(mode='json')
    for key in ('contract_id', 'state'):
        definition.pop(key)
    for module in definition['modules']:
        for outcome in module['outcomes']:
            for key in ('lesson_ids', 'practice', 'teaching_status', 'assessment_status'):
                outcome.pop(key)
    presentation = {'lessons.json', 'panel-modules.json', 'course-structure.json',
                    'outcomes.json', 'credit-equivalence.json', 'bridge-path.json'}
    manifest = package.manifest
    return encode({'outcomes': definition, 'rubric_id': manifest.rubric_id,
        'maximum_stars': manifest.maximum_stars, 'star_bonus_xp': manifest.star_bonus_xp,
        'modules': [{'id': item.id, 'base_xp': item.base_xp, 'prerequisites': item.prerequisites}
                    for item in manifest.modules],
        'assets': {name: digest for name, digest in manifest.artifacts.items() if name not in presentation}})[1]


def equivalence_plan(source, target, progress, *, _verified_snapshots=None):
    """Inspect trusted repository progress without changing either enrollment."""
    if progress.course_version != source.manifest.release_id or not progress.enrollment_id:
        raise CourseCatalogError('Equivalence requires the original pinned enrollment')
    target_contract = package_outcomes(target)
    if target_contract is None:
        raise CourseCatalogError('The bridge requires explicit target outcomes')
    rules = {}
    policy = None
    if 'credit-equivalence.json' in target.manifest.artifacts:
        policy = EquivalencePolicy.model_validate_json(target.read('credit-equivalence.json'))
        if (policy.source_version == source.manifest.release_id
                and policy.source_manifest_sha256 == source.manifest_sha256):
            basis = assessment_basis(source)
            if (policy.target_version != target.manifest.release_id or not basis
                    or basis != policy.assessment_basis_sha256 or basis != assessment_basis(target)
                    or source.manifest.release_id == target.manifest.release_id):
                raise CourseCatalogError('The authored credit mapping does not match unchanged assessment requirements')
            rules = {rule.outcome_id: rule for rule in policy.rules}
            if not set(rules) <= set(target_contract.required_outcomes()):
                raise CourseCatalogError('The credit mapping names an unknown target outcome')
        # A rule for a different source release never grants this learner credit.
    outcomes = []
    for module in target_contract.modules:
        saved = progress.modules.get(module.module_id, {})
        snapshot = None
        needs_evidence = any(item.id in rules for item in module.outcomes)
        if needs_evidence and isinstance(saved, dict) and saved.get('completed') is True and saved.get('outcome_credit'):
            snapshot = (_verified_snapshots or {}).get(module.module_id)
            if snapshot is None:
                snapshot = verified_credit_snapshot(source, progress, module.module_id,
                    saved['outcome_credit'], expected_attempt_id=saved.get('completion_attempt_id'))
        for outcome in module.outcomes:
            rule = rules.get(outcome.id)
            eligible = rule is not None and snapshot is not None
            row = {'outcome_id': outcome.id, 'module_id': module.module_id,
                   'statement': outcome.statement,
                   'status': 'eligible_for_transfer' if eligible else 'requires_assessment',
                   'reason': rule.reason if eligible else (
                       'Original assessed evidence is required; prior XP or completion alone is insufficient.' if rule
                       else 'No authored equivalence rule applies to this source course and outcome.'),
                   'rule_id': rule.rule_id if rule else None}
            if eligible:
                row['source_completion_attempt_id'] = saved['completion_attempt_id']
                row['source_assessment_sha256'] = encode(snapshot)[1]
            outcomes.append(row)
    result = {'schema_version': 1, 'kind': 'outcome_equivalence_preview',
        'source_enrollment_id': progress.enrollment_id,
        'source_version': source.manifest.release_id, 'source_manifest_sha256': source.manifest_sha256,
        'target_version': target.manifest.release_id, 'target_manifest_sha256': target.manifest_sha256,
        'policy_id': policy.policy_id if rules else None, 'outcomes': outcomes,
        'eligible_outcome_count': sum(item['status'] == 'eligible_for_transfer' for item in outcomes),
        'required_outcome_count': len(outcomes), 'read_only': True, 'can_apply': False,
        'credit_transferred': False, 'xp_awarded': 0, 'staff_review_required': False,
        'next_step': 'Eligibility is a preview. Required assessments remain due until an explicit supported transfer records credit.'}
    result['plan_sha256'] = encode(result)[1]
    return result
