"""An optional study path through the same pinned course and assessments."""
from typing import Literal

from pydantic import Field, model_validator

from .catalog import CourseCatalogError
from .outcomes import ContractModel, package_outcomes
from .progression_policy import package_progression_policy


# The checklist sequence: scope/approval, source verification and quality
# limits, recovery/delivery, then the capstone. Order is part of the contract.
STAGE_ORDER = ('scope', 'verify', 'recover_deliver', 'capstone')


class BridgeStage(ContractModel):
    id: Literal['scope', 'verify', 'recover_deliver', 'capstone']
    title: str = Field(min_length=1)
    purpose: str = Field(min_length=20)
    module_ids: tuple[str, ...] = Field(min_length=1)


class BridgePath(ContractModel):
    schema_version: Literal[1] = 1
    path_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=20)
    credential_policy: Literal['same_course_same_required_outcomes']
    duration_minutes: None  # Unmeasured until a pilot; never promise a completion time.
    capstone_outcome_id: str = Field(min_length=1)
    stages: tuple[BridgeStage, ...] = Field(min_length=1)

    @model_validator(mode='after')
    def ordered_stages(self):
        if tuple(stage.id for stage in self.stages) != STAGE_ORDER or len(self.stages[-1].module_ids) != 1:
            raise ValueError('The bridge must cover scope, verification, recovery/delivery and end with one capstone module')
        return self


def public_bridge_path(package):
    if 'bridge-path.json' not in package.manifest.artifacts:
        return None
    path = BridgePath.model_validate_json(package.read('bridge-path.json'))
    contract = package_outcomes(package)
    policy = package_progression_policy(package)
    covered = [module for stage in path.stages for module in stage.module_ids]
    if (contract is None or policy is None or len(covered) != len(set(covered))
            or set(covered) != set(policy.module_order)
            or len({stage.id for stage in path.stages}) != len(path.stages)):
        raise CourseCatalogError('The bridge must cover every required module exactly once under the flexible-order policy')
    capstone = next((module.module_id for module in contract.modules
                     if any(item.id == path.capstone_outcome_id for item in module.outcomes)), None)
    if capstone != path.stages[-1].module_ids[0]:
        raise CourseCatalogError('The final bridge stage must assess the named capstone outcome')
    modules = {module.id: module for module in package.manifest.modules}
    outcomes = {module.module_id: module.outcomes for module in contract.modules}
    return {'path_id': path.path_id, 'title': path.title, 'description': path.description,
        'state': contract.state, 'course_version': package.manifest.release_id,
        'manifest_sha256': package.manifest_sha256, 'required_outcomes': len(contract.required_outcomes()),
        'credit_policy': 'same_course_same_required_outcomes', 'duration_minutes': None,
        'duration_status': 'unmeasured_until_pilot', 'capstone_outcome_id': path.capstone_outcome_id,
        'rules': [
            'Reading is optional preparation. Every required assessment still needs passing evidence; this path does not waive an outcome.',
            'Your earlier course, credit and certificate remain intact. Prior XP or a matching module title does not establish a new skill.',
            'Review automatic feedback and open the related lessons as needed. There is no timer, promised duration or staff grading queue.',
            'Any transferred credit needs an explicit equivalence rule and verified original evidence. A preview alone never awards credit.',
        ],
        'stages': [{'id': stage.id, 'title': stage.title, 'purpose': stage.purpose,
                    'modules': [{'module_id': mid, 'title': modules[mid].title,
                                 'required_outcomes': len(outcomes[mid])} for mid in stage.module_ids]}
                   for stage in path.stages]}
