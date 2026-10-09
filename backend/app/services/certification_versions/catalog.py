"""Verify immutable course packages before exposing them to an enrollment.

Lifecycle metadata is separate from content: retiring a release for new learners
must not modify the package existing learners use. Drafts are never enrollable.
"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CATALOG_ROOT = Path(__file__).resolve().parents[3] / 'certification-data' / 'courses'
RELEASE_ID = re.compile(r'^[a-z0-9][a-z0-9.-]{0,95}$')


class CourseCatalogError(ValueError):
    pass


class ReleaseEntry(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    state: Literal['draft', 'published', 'retired']
    supported_for_existing: bool
    manifest_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')

    @model_validator(mode='after')
    def validate_support(self):
        if self.state == 'published' and not self.supported_for_existing:
            raise ValueError('A course accepting new learners must support their enrollment')
        return self


class CourseModule(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    id: str = Field(pattern=r'^[a-z][a-z0-9_]*$')
    title: str
    base_xp: int = Field(ge=0)
    lesson_ids: tuple[str, ...]
    prerequisites: tuple[str, ...] = ()


class CourseManifest(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    schema_version: Literal[1] = 1
    course_id: Literal['vandal-workflow-architect'] = 'vandal-workflow-architect'
    release_id: str
    title: str
    description: str
    historical_provenance: Literal['continuation-baseline', 'authored-release']
    rubric_id: str
    star_bonus_xp: int = Field(ge=0)
    maximum_stars: int = Field(ge=1)
    modules: tuple[CourseModule, ...]
    # Serialized JSON is retained by CoursePackage; callers get fresh objects.
    artifacts: dict[str, str]

    @model_validator(mode='after')
    def validate_structure(self):
        if not RELEASE_ID.fullmatch(self.release_id):
            raise ValueError('Invalid release identity')
        ids = [module.id for module in self.modules]
        lessons = [lesson for module in self.modules for lesson in module.lesson_ids]
        if not ids or len(ids) != len(set(ids)) or len(lessons) != len(set(lessons)) or any(not lesson.strip() for lesson in lessons):
            raise ValueError('Module and lesson identities must be nonempty and unique')
        preceding = set()
        for module in self.modules:
            if not module.lesson_ids or not set(module.prerequisites) <= preceding:
                raise ValueError(f'Invalid lessons or prerequisites for {module.id}')
            preceding.add(module.id)
        required = {'lessons.json', 'exercises.json', 'panel-modules.json', 'course-structure.json', 'rubric.py'}
        if not required <= self.artifacts.keys():
            raise ValueError('Course package is missing required artifacts')
        for path, digest in self.artifacts.items():
            if Path(path).is_absolute() or '..' in Path(path).parts or not re.fullmatch(r'[a-f0-9]{64}', digest):
                raise ValueError('Invalid artifact path or digest')
        return self


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class CoursePackage:
    """Bytes and tuples prevent a caller from mutating another reader's course."""
    manifest_bytes: bytes
    manifest_sha256: str
    entry: ReleaseEntry
    artifact_bytes: tuple[tuple[str, bytes], ...]
    catalog_root: Path | None = None

    @property
    def manifest(self) -> CourseManifest:
        return CourseManifest.model_validate_json(self.manifest_bytes)

    def read(self, name: str) -> bytes:
        for path, data in self.artifact_bytes:
            if path == name:
                return data
        raise CourseCatalogError(f'Course asset is unavailable: {name}')

    def json(self, name: str):
        return json.loads(self.read(name))

    def summary(self) -> dict:
        manifest = self.manifest
        return {
            'course_version': manifest.release_id,
            'course_title': manifest.title,
            'manifest_sha256': self.manifest_sha256,
            'state': self.entry.state,
            'supported_for_existing': self.entry.supported_for_existing,
            'modules_total': len(manifest.modules),
            'module_ids': [module.id for module in manifest.modules],
            'maximum_xp': sum(m.base_xp + manifest.maximum_stars * manifest.star_bonus_xp for m in manifest.modules),
            'historical_provenance': manifest.historical_provenance,
        }


class CourseCatalog:
    def __init__(self, root: Path = CATALOG_ROOT):
        self.root = root

    def registry(self) -> dict:
        try:
            data = json.loads((self.root / 'registry.json').read_bytes())
            if not isinstance(data, dict) or data.get('schema_version') != 1 or not isinstance(data.get('releases'), dict):
                raise ValueError('Invalid registry')
            for release_id, entry in data['releases'].items():
                if not RELEASE_ID.fullmatch(release_id):
                    raise ValueError('Invalid release identity')
                ReleaseEntry.model_validate(entry)
            for key in ('legacy_continuation', 'new_enrollment_default'):
                if key in data:
                    version = data[key]
                    if not isinstance(version, str) or version not in data['releases']:
                        raise ValueError('The default course must reference a registered version')
                    entry = ReleaseEntry.model_validate(data['releases'][version])
                    if entry.state == 'draft' or not entry.supported_for_existing:
                        raise ValueError('The default course must support enrollment')
                    if key == 'new_enrollment_default' and entry.state != 'published':
                        raise ValueError('The new learner default must be published')
            if data.get('transition_policy', 'optional') != 'optional':
                raise ValueError('Only the approved optional transition policy is supported')
            offers = data.get('optional_upgrade_offers', {})
            if not isinstance(offers, dict):
                raise ValueError('Optional course offers must be keyed by source course')
            for source, targets in offers.items():
                if (source not in data['releases'] or not isinstance(targets, list)
                        or any(not isinstance(target, str) or target not in data['releases'] or target == source for target in targets)
                        or len(targets) != len(set(targets))):
                    raise ValueError('Optional course offers must name distinct registered target courses')
            return data
        except (OSError, ValueError) as exc:
            raise CourseCatalogError('Course catalog is unavailable or invalid') from exc

    def load(self, release_id: str, *, new_enrollment: bool = False, preview: bool = False) -> CoursePackage:
        registry = self.registry()
        raw_entry = registry['releases'].get(release_id)
        if raw_entry is None:
            raise CourseCatalogError('Unknown course version')
        entry = ReleaseEntry.model_validate(raw_entry)
        if not preview:
            if entry.state == 'draft':
                raise CourseCatalogError('Draft courses are not available for enrollment')
            if new_enrollment and entry.state != 'published':
                raise CourseCatalogError('This course is closed to new enrollments')
            if not new_enrollment and not entry.supported_for_existing:
                raise CourseCatalogError('This course requires a supported continuation path')
        try:
            directory = (self.root / release_id).resolve()
            if directory.parent != self.root.resolve():
                raise ValueError('Invalid course directory')
            raw_manifest = (directory / 'manifest.json').read_bytes()
            if sha256(raw_manifest) != entry.manifest_sha256:
                raise ValueError('Published manifest changed')
            manifest = CourseManifest.model_validate_json(raw_manifest)
            if manifest.release_id != release_id:
                raise ValueError('Release identity mismatch')
            assets = []
            for name, expected in manifest.artifacts.items():
                path = (directory / name).resolve()
                if not path.is_relative_to(directory):
                    raise ValueError('Asset escapes course directory')
                data = path.read_bytes()
                if sha256(data) != expected:
                    raise ValueError(f'Course asset changed: {name}')
                assets.append((name, data))
            package = CoursePackage(raw_manifest, entry.manifest_sha256, entry, tuple(assets), self.root)
            self._validate_content(package)
            return package
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise CourseCatalogError(f'Course package failed integrity verification: {release_id}') from exc

    @staticmethod
    def _validate_content(package: CoursePackage) -> None:
        from .outcomes import package_outcomes
        from .progression_policy import package_progression_policy
        package_progression_policy(package)
        contract = package_outcomes(package)
        manifest = package.manifest
        for path in manifest.artifacts:
            if path.startswith('governance-cases/'):
                from .governance_case import load_governance_case
                if path != 'governance-cases/governance.json':
                    raise ValueError('Unsupported bounded Governance case identity')
                load_governance_case(package)
            if path.startswith('batch-cases/'):
                from .batch_case import load_batch_case
                if path != 'batch-cases/batch_processing.json':
                    raise ValueError('Unsupported bounded batch case identity')
                load_batch_case(package)
            if path.startswith('validation-cases/'):
                from .validation_case import load_validation_case
                if path != 'validation-cases/validation_qa.json':
                    raise ValueError('Unsupported representative validation case identity')
                load_validation_case(package)
            if path.startswith('output-cases/'):
                from .output_case import load_output_case
                if path != 'output-cases/output_delivery.json':
                    raise ValueError('Unsupported Output and Delivery case identity')
                load_output_case(package)
            if path.startswith('advanced-cases/'):
                from .advanced_case import load_advanced_case
                if path != 'advanced-cases/advanced_nodes.json':
                    raise ValueError('Unsupported Advanced Nodes case identity')
                load_advanced_case(package)
            if path.startswith('connected-cases/'):
                from .multi_step_case import load_multi_step_case
                if path != 'connected-cases/multi_step.json':
                    raise ValueError('Unsupported connected-workflow case identity')
                load_multi_step_case(package)
            if path.startswith('design-cases/'):
                from .workflow_design_case import load_workflow_design_case
                if path != 'design-cases/workflow_design.json':
                    raise ValueError('Unsupported design case identity')
                load_workflow_design_case(package)
            if path.startswith('process-cases/'):
                from .process_case import load_process_case
                module_id = path.removeprefix('process-cases/').removesuffix('.json')
                if path != f'process-cases/{module_id}.json':
                    raise ValueError('Process case identity differs from its module')
                load_process_case(package, module_id)
            if path.startswith('repair-cases/'):
                from .repair_case import load_repair_case
                module_id = path.removeprefix('repair-cases/').removesuffix('.json')
                if path != f'repair-cases/{module_id}.json':
                    raise ValueError('Repair case identity differs from its module')
                load_repair_case(package, module_id)
            if path.startswith('proposals/'):
                from .scope_proposal import load_proposal_case
                module_id = path.removeprefix('proposals/').removesuffix('.json')
                if path != f'proposals/{module_id}.json':
                    raise ValueError('Proposal asset identity differs from its module')
                load_proposal_case(package, module_id)
            if path.startswith('decisions/'):
                from .learner_decisions import load_prompt, execution_requirement
                module_id = path.removeprefix('decisions/').removesuffix('.json')
                prompts = package.json(path)
                if not isinstance(prompts, list) or not prompts or path != f'decisions/{module_id}.json':
                    raise ValueError('Decision prompts require a nonempty module definition')
                load_prompt(package, module_id, prompts[0]['id'])
                execution_requirement(package, module_id)
            if path.startswith('assessments/'):
                from .scenario_assessment import ScenarioBank
                if contract is None:
                    raise ValueError('Scenario assessments require an outcome contract')
                bank = ScenarioBank.model_validate_json(package.read(path))
                if path != f'assessments/{bank.module_id}.json':
                    raise ValueError('Scenario asset identity differs from its module')
                bank.verify_contract(contract)
        lessons, exercises, panel = (package.json(name) for name in ('lessons.json', 'exercises.json', 'panel-modules.json'))
        if (exercises.get('governance', {}).get('assessment_method') == 'authenticated_bounded_supervision_and_private_handoff'
                and 'governance-cases/governance.json' not in manifest.artifacts):
            raise ValueError('A Governance capstone requires its original packaged case')
        if (exercises.get('batch_processing', {}).get('assessment_method') == 'authenticated_pilot_batch_inventory_and_targeted_recovery'
                and 'batch-cases/batch_processing.json' not in manifest.artifacts):
            raise ValueError('A bounded batch exercise requires its original packaged case')
        if (exercises.get('validation_qa', {}).get('assessment_method') == 'authenticated_representative_suite_repair_retest'
                and 'validation-cases/validation_qa.json' not in manifest.artifacts):
            raise ValueError('A representative validation exercise requires its original packaged case')
        if (exercises.get('output_delivery', {}).get('assessment_method') == 'authenticated_artifact_release_delivery_review'
                and 'output-cases/output_delivery.json' not in manifest.artifacts):
            raise ValueError('An Output and Delivery exercise requires its original packaged case')
        if (exercises.get('advanced_nodes', {}).get('assessment_method') == 'authenticated_method_calculation_dependency_review'
                and 'advanced-cases/advanced_nodes.json' not in manifest.artifacts):
            raise ValueError('An Advanced Nodes exercise requires its original packaged case')
        if (exercises.get('multi_step', {}).get('assessment_method') == 'authenticated_connected_workflow_run_review'
                and 'connected-cases/multi_step.json' not in manifest.artifacts):
            raise ValueError('A connected-workflow exercise requires its original packaged case')
        if (exercises.get('foundations', {}).get('assessment_method') == 'owned_scoped_extraction'
                and 'proposals/foundations.json' not in manifest.artifacts):
            raise ValueError('A scoped Foundations exercise requires its original packaged proposal')
        module_ids = {module.id for module in manifest.modules}
        if set(lessons) != module_ids or set(exercises) != module_ids:
            raise ValueError('Teaching and exercises must cover exactly the manifest modules')
        tiers = package.json('course-structure.json')['tiers']
        tier_module_ids = [module_id for tier in tiers for module_id in tier['moduleIds']]
        if len(tier_module_ids) != len(module_ids) or set(tier_module_ids) != module_ids:
            raise ValueError('Journey tiers must contain each course module exactly once')
        if [m['id'] for m in panel] != [m.id for m in manifest.modules]:
            raise ValueError('Panel and manifest module order differ')
        for module, panel_module in zip(manifest.modules, panel):
            authored = lessons[module.id]['lessons']
            if tuple(lesson['id'] for lesson in authored) != module.lesson_ids:
                raise ValueError('Lesson identities differ from manifest')
            if [lesson['id'] for lesson in panel_module['lessons']] != list(module.lesson_ids):
                raise ValueError('Panel lesson identities differ from manifest')
            if panel_module['xp'] != module.base_xp or panel_module['title'] != module.title:
                raise ValueError('Panel module metadata differs from manifest')
            for lesson, panel_lesson in zip(authored, panel_module['lessons']):
                if type(lesson.get('revision')) is not int or lesson['revision'] < 1:
                    raise ValueError('Each lesson requires a positive authored revision')
                for key in ('id', 'revision', 'title', 'content', 'objective', 'variant', 'diagram'):
                    if lesson.get(key, '' if key == 'objective' else None) != panel_lesson.get(key, '' if key == 'objective' else None):
                        raise ValueError(f'Chat/panel lesson mismatch: {key}')
                if lesson.get('knowledge_check') != panel_lesson.get('knowledgeCheck'):
                    raise ValueError('Chat/panel practice mismatch')
            for filename in exercises[module.id].get('documents', []):
                package.read('documents/' + filename)
