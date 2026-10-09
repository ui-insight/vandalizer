#!/usr/bin/env python3
"""Assemble a complete isolated 5.0 preview, never an application release.

The output has its own draft-only catalog for integrity checks and UI QA. This
tool cannot write inside the application catalog or overwrite earlier evidence.
It neither publishes nor initializes enrollment, execution, grading or credit.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'backend/certification-data'
sys.path.insert(0, str(ROOT / 'backend'))
from app.services.certification_versions.catalog import CATALOG_ROOT, RELEASE_ID, CourseCatalog  # noqa: E402
from app.services.certification_versions.delivery import public_modules  # noqa: E402
from app.services.certification_versions.outcomes import OutcomeContract  # noqa: E402
from app.services.certification_versions.scenario_assessment import ScenarioBank  # noqa: E402
from app.services.certification_versions.progression_policy import ProgressionPolicy, public_progression_policy  # noqa: E402
from app.services.certification_versions.credential_scope import public_credential_scope  # noqa: E402
from app.services.certification_versions.bridge_path import public_bridge_path  # noqa: E402

CASES = {
    'proposals/foundations.json': 'foundations-proposal.json',
    'decisions/foundations.json': 'foundations-decisions.json',
    'decisions/extraction_engine.json': 'extraction-engine-decisions.json',
    'repair-cases/extraction_engine.json': 'extraction-engine-repair.json',
    'process-cases/process_mapping.json': 'process-mapping-case.json',
    'design-cases/workflow_design.json': 'workflow-design-case.json',
    'connected-cases/multi_step.json': 'multi-step-case.json',
    'advanced-cases/advanced_nodes.json': 'advanced-nodes-case.json',
    'output-cases/output_delivery.json': 'output-delivery-case.json',
    'validation-cases/validation_qa.json': 'validation-qa-case.json',
    'batch-cases/batch_processing.json': 'batch-processing-case.json',
    'governance-cases/governance.json': 'governance-capstone-case.json',
    'assessments/ai_literacy.json': 'ai-literacy-scenarios.json',
    'assessments/validation_qa.json': 'validation-qa-scenarios.json',
    'assessments/governance.json': 'governance-scenarios.json',
    'outcomes.json': 'outcomes.json',
    'assessment-policy.json': 'assessment-policy.json',
    'progression-policy.json': 'progression-policy.json',
    'course-structure.json': 'course-structure.json',
    'bridge-path.json': 'bridge-path.json',
}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assemble(output, release_id, *, data_root=DATA):
    output = Path(output).resolve()
    if output == CATALOG_ROOT.resolve() or output.is_relative_to(CATALOG_ROOT.resolve()):
        raise ValueError('Preview output must remain outside the application course catalog')
    if output.exists() or not RELEASE_ID.fullmatch(release_id):
        raise ValueError('Use a new output directory and a valid preview identity')
    draft = data_root / 'drafts/v5.0'
    contract = OutcomeContract.model_validate_json((draft / 'outcomes.json').read_bytes())
    progression = ProgressionPolicy.model_validate_json((draft / 'progression-policy.json').read_bytes())
    if contract.state != 'design_draft':
        raise ValueError('This tool only assembles unpublished design drafts')
    panel = json.loads((data_root / 'panel-modules.json').read_text())
    if tuple(module['id'] for module in panel) != progression.module_order:
        raise ValueError('The progression policy must name the complete authored module order')
    lessons = json.loads((data_root / 'lessons.json').read_text())
    exercises = {}
    if {module['id'] for module in panel} != {module.module_id for module in contract.modules}:
        raise ValueError('The preview must include every outcome module exactly once')
    for module in panel:
        module_id = module['id']
        authored = json.loads((draft / f'{module_id.replace("_", "-")}-teaching.json').read_text())
        original = {lesson['id']: lesson for lesson in lessons[module_id]['lessons']}
        replacement = authored['replacements']
        if (authored['module_id'] != module_id or len(replacement) != len(original)
                or {lesson['id'] for lesson in replacement} != set(original)
                or any(lesson['revision'] <= original[lesson['id']]['revision'] for lesson in replacement)):
            raise ValueError('Every teaching replacement must preserve identity and advance its revision')
        module.update(deepcopy(authored['module_patch']))
        module['xp'] = progression.module_xp[module_id]
        module['lessons'] = [{**{key: value for key, value in lesson.items() if key != 'knowledge_check'},
                              **({'knowledgeCheck': lesson['knowledge_check']} if 'knowledge_check' in lesson else {})}
                             for lesson in replacement]
        # Reflective participation requirements never survive as new outcome credit.
        lessons[module_id] = {key: deepcopy(module[key]) for key in ('title', 'subtitle', 'description', 'objectives', 'tips')}
        lessons[module_id].update(estimated_minutes=module['estimatedMinutes'], lessons=deepcopy(replacement), assessment=None)
        exercise = json.loads((draft / f'{module_id.replace("_", "-")}-exercise.json').read_text())
        if exercise.get('star_criteria') != {} or exercise.get('expected_values') != {}:
            raise ValueError('A draft exercise cannot inherit legacy answer keys or star scoring')
        exercises[module_id] = exercise
    contract.verify_teaching_references(lessons)
    bank = ScenarioBank.model_validate_json((draft / 'ai-literacy-scenarios.json').read_bytes())
    recognition = exercises['ai_literacy']
    if (recognition.get('assessment_method') != 'authenticated_scenario_recognition'
            or recognition.get('scenario_bank_id') != bank.bank_id
            or recognition.get('scenario_bank_sha256') != bank.digest
            or recognition.get('documents') != []):
        raise ValueError('AI Literacy must bind its original recognition bank without workspace prerequisites')

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.certification-preview-', dir=output.parent) as temporary:
        staging = Path(temporary)
        package_path = staging / release_id
        package_path.mkdir()
        write_json(package_path / 'lessons.json', lessons)
        write_json(package_path / 'panel-modules.json', panel)
        write_json(package_path / 'exercises.json', exercises)
        shutil.copytree(data_root / 'documents', package_path / 'documents')
        for source in (draft / 'documents').iterdir():
            if source.is_file():
                shutil.copyfile(source, package_path / 'documents' / source.name)
        for target, source in CASES.items():
            (package_path / target).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(draft / source, package_path / target)
        (package_path / 'rubric.py').write_text(
            '"""Unpublished preview: final-credit integration and live calibration are incomplete."""\n'
            'async def validate_module(*args, **kwargs):\n'
            '    raise RuntimeError("This preview cannot grade or award course credit")\n')
        artifacts = {str(path.relative_to(package_path)): digest(path)
                     for path in sorted(package_path.rglob('*')) if path.is_file()}
        manifest = {'schema_version': 1, 'course_id': 'vandal-workflow-architect',
                    'release_id': release_id, 'title': 'Vandalizer 5.0 certification — unpublished preview',
                    'description': contract.credential_promise, 'historical_provenance': 'authored-release',
                    'rubric_id': contract.rubric_id, 'star_bonus_xp': 0, 'maximum_stars': 1,
                    'modules': [{'id': item['id'], 'title': item['title'], 'base_xp': item['xp'],
                                 'lesson_ids': [lesson['id'] for lesson in item['lessons']], 'prerequisites': []}
                                for item in panel], 'artifacts': artifacts}
        write_json(package_path / 'manifest.json', manifest)
        manifest_digest = digest(package_path / 'manifest.json')
        write_json(staging / 'registry.json', {'schema_version': 1, 'releases': {release_id: {
            'state': 'draft', 'supported_for_existing': False, 'manifest_sha256': manifest_digest}}})
        package = CourseCatalog(staging).load(release_id, preview=True)
        modules = public_modules(package)
        structure = package.json('course-structure.json')
        write_json(staging / 'public-course.json', {**package.summary(), 'versioned': True, 'modules': modules,
                   'levels': structure['levels'], 'tiers': structure['tiers'],
                   'progression_policy': public_progression_policy(package),
                   'credential_scope': public_credential_scope(package),
                   'bridge_path': public_bridge_path(package),
                   'prerequisites': {module.id: list(module.prerequisites) for module in package.manifest.modules}})
        write_json(staging / 'preview-report.json', {
            'preview_only': True, 'release_id': release_id, 'manifest_sha256': manifest_digest,
            'modules': len(modules), 'lessons': sum(len(item['lessons']) for item in modules),
            'required_outcomes': len(contract.required_outcomes()), 'release_verified_outcomes': 0,
            'grading_available': False, 'enrollment_available': False,
            'application_registry_changed': False, 'credit_policy_finalized': False,
            'progression_policy_finalized': False,
            'progression_policy_id': progression.policy_id,
            'progression_policy_state': progression.state,
            'display_policy': 'Pinned design draft: flexible learning order, all required outcomes for credit, base XP once, no star enrichment, and XP milestones separate from credentials. Release verification and approval remain open.',
            'source_sha256': {str(path.relative_to(data_root)): digest(path)
                              for path in sorted(draft.rglob('*')) if path.is_file()},
        })
        # Rename only after the complete package and public delivery validate.
        staging.rename(output)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--release-id', default='v5.0-preview-2026-10-07.1')
    args = parser.parse_args()
    print(assemble(args.output, args.release_id))
