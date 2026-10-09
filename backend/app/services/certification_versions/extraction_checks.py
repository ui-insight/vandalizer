"""Execution completeness for the assigned NIH repair, separate from quality."""
import hashlib
from pathlib import Path

from .attempts import encode
from .catalog import CourseCatalogError
from .repair_case import repair_reference_matches

OUTCOME_ID = 'extraction_engine.assigned_run'
REQUIREMENT_KEYS = ('id', 'statement', 'method', 'evidence', 'passing_conditions', 'critical_failures')
REQUIREMENTS_SHA256 = '3feca5f5a0ba883c3f0aec3b5896eb6f88d5250525fee9d76c10137a0e7fd7db'


def check_extraction_execution(contract, run, snapshot):
    """Consume collector-verified owned records; never decide value accuracy."""
    module = next((item for item in contract.modules if item.module_id == 'extraction_engine'), None)
    required = [item for item in module.outcomes if item.method == 'deterministic'] if module else []
    if (len(required) != 1 or required[0].id != OUTCOME_ID
            or encode({key: required[0].model_dump(mode='json')[key] for key in REQUIREMENT_KEYS})[1] != REQUIREMENTS_SHA256):
        raise CourseCatalogError('The Extraction Engine execution requirement has no matching verified checker')
    plan, result, authorization = run['plan'], run['result'], run.get('authorization')
    scope = authorization['decision'] if authorization else None
    repair = plan.get('repair_case')
    if (run['state'] != 'completed' or result is None or result['status'] != 'completed'
            or plan['module_id'] != 'extraction_engine' or snapshot['module_id'] != 'extraction_engine'
            or plan['input_snapshot_id'] != snapshot['uuid'] or plan['input_snapshot_sha256'] != encode(snapshot)[1]
            or encode(snapshot['artifact'])[1] != snapshot['artifact_sha256']
            or len(snapshot['documents']) != 1 or not repair
            or result['documents_executed'] != [item['document_id'] for item in snapshot['documents']]
            or repair['input_snapshot_sha256'] != encode(snapshot)[1]
            or repair['artifact_sha256'] != snapshot['artifact_sha256']
            or not scope or not plan.get('approval_requirement')
            or result['run_id'] != run['run_id'] or result['plan_sha256'] != run['plan_sha256']
            or result.get('authorization_sha256') != encode(authorization)[1]
            or scope['run_id'] != run['run_id'] or scope['plan_sha256'] != run['plan_sha256']
            or scope['input_snapshot_sha256'] != plan['input_snapshot_sha256']
            or scope['run_state_at_submission'] != 'prepared'
            or scope['submission']['choice'] != plan['approval_requirement']['choice']
            or not repair_reference_matches(repair, scope['submission'].get('repair_case_sha256'))):
        raise CourseCatalogError('The NIH execution evidence does not bind the approved revision and repair example')
    keys = [field['searchphrase'].strip() for field in snapshot['artifact']['fields']]
    entities = result['entities']
    # A present null optional value is a complete output slot, not a claim of
    # correctness. Missing keys and zero/multiple project records need revision.
    complete = (bool(keys) and len(set(keys)) == len(keys) and len(entities) == 1
                and isinstance(entities[0], dict) and set(keys) <= set(entities[0]))
    return {'outcome_id': OUTCOME_ID, 'method': 'deterministic',
            'status': 'requirements_supported' if complete else 'revision_required', 'passed': complete,
            'checker_id': 'approved-assigned-nih-repair-run.1', 'requirements_sha256': REQUIREMENTS_SHA256,
            'implementation_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'run_id': run['run_id'], 'plan_sha256': run['plan_sha256'], 'result_sha256': encode(result)[1],
            'input_snapshot_sha256': encode(snapshot)[1], 'artifact_sha256': snapshot['artifact_sha256'],
            'authorization_sha256': result['authorization_sha256'], 'repair_case_sha256': encode(repair)[1],
            'explanation': ('The approved assigned NIH run preserves one complete result for its exact field revision. Value accuracy needs separate source review.'
                            if complete else 'The assigned run does not preserve exactly one result containing every requested field.'),
            'revision_instruction': '' if complete else 'Inspect the saved output, correct the extraction and run it again so every requested field has a value or an explicit absence.',
            'credit_awarded': False, 'module_completion_eligible': False}
