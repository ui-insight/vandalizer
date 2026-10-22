"""Pinned deterministic Foundations execution check; no model or credit award."""
import hashlib
from pathlib import Path

from .attempts import encode
from .catalog import CourseCatalogError

OUTCOME_ID = 'foundations.executed_extraction'
REQUIREMENT_KEYS = ('id', 'statement', 'method', 'evidence', 'passing_conditions', 'critical_failures')
# Changes to the assessed requirement require an explicitly reviewed checker,
# rather than silently reusing this implementation for a different competency.
REQUIREMENTS_SHA256 = 'e62671b002ebce6c3e4b163e5659b613063c4a0947210169fe1e3ec2b906bc45'


def check_foundations_execution(contract, run, snapshot):
    """Caller supplies owned, integrity-verified records from the collector."""
    module = next((item for item in contract.modules if item.module_id == 'foundations'), None)
    required = [item for item in module.outcomes if item.method == 'deterministic'] if module else []
    if (len(required) != 1 or required[0].id != OUTCOME_ID
            or encode({key: required[0].model_dump(mode='json')[key] for key in REQUIREMENT_KEYS})[1] != REQUIREMENTS_SHA256):
        raise CourseCatalogError('The deterministic Foundations requirement has no matching verified checker')
    plan, result, authorization = run['plan'], run['result'], run.get('authorization')
    scope = authorization['decision'] if authorization else None
    if (run['state'] != 'completed' or result is None or result['status'] != 'completed'
            or plan['input_snapshot_id'] != snapshot['uuid'] or plan['input_snapshot_sha256'] != encode(snapshot)[1]
            or encode(snapshot['artifact'])[1] != snapshot['artifact_sha256']
            or result['documents_executed'] != [item['document_id'] for item in snapshot['documents']]
            or not snapshot['documents'] or not scope or not plan.get('approval_requirement')
            or result['run_id'] != run['run_id'] or result['plan_sha256'] != run['plan_sha256']
            or result.get('authorization_sha256') != encode(authorization)[1]
            or scope['run_id'] != run['run_id'] or scope['plan_sha256'] != run['plan_sha256']
            or scope['input_snapshot_sha256'] != plan['input_snapshot_sha256']
            or scope['run_state_at_submission'] != 'prepared'
            or scope['submission']['choice'] != plan['approval_requirement']['choice']):
        raise CourseCatalogError('The deterministic execution evidence does not bind an approved assigned run')
    return {'outcome_id': OUTCOME_ID, 'method': 'deterministic', 'status': 'requirements_supported', 'passed': True,
            'checker_id': 'approved-assigned-foundations-run.1', 'requirements_sha256': REQUIREMENTS_SHA256,
            'implementation_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'run_id': run['run_id'], 'plan_sha256': run['plan_sha256'], 'result_sha256': encode(result)[1],
            'input_snapshot_sha256': encode(snapshot)[1], 'artifact_sha256': snapshot['artifact_sha256'],
            'authorization_sha256': result['authorization_sha256'],
            'explanation': 'The completed run binds the reviewed extraction revision and the exact assigned inputs.',
            'credit_awarded': False, 'module_completion_eligible': False}
