"""An optional study path through the same pinned course and assessments."""
from typing import Literal

from pydantic import Field

from .catalog import CourseCatalogError
from .outcomes import ContractModel, package_outcomes
from .progression_policy import package_progression_policy


class BridgeStage(ContractModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    purpose: str = Field(min_length=20)
    module_ids: tuple[str, ...] = Field(min_length=1)


class BridgePath(ContractModel):
    schema_version: Literal[1] = 1
    path_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=20)
    credential_policy: Literal['same_course_same_required_outcomes']
    duration_minutes: None
    stages: tuple[BridgeStage, ...] = Field(min_length=1)


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
    modules = {module.id: module for module in package.manifest.modules}
    outcomes = {module.module_id: module.outcomes for module in contract.modules}
    return {'path_id': path.path_id, 'title': path.title, 'description': path.description,
        'state': contract.state, 'course_version': package.manifest.release_id,
        'manifest_sha256': package.manifest_sha256, 'required_outcomes': len(contract.required_outcomes()),
        'credit_policy': 'same_course_same_required_outcomes', 'duration_minutes': None,
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
