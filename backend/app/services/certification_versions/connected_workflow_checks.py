"""Check one real connected execution and bind an owned repair comparison."""
import hashlib
from pathlib import Path

from .attempts import encode
from .catalog import CourseCatalogError
from .connected_workflow_checkpoints import decode_checkpoints

OUTCOME_ID = 'multi_step.connected_execution'
REQUIREMENT_KEYS = ('id', 'statement', 'method', 'evidence', 'passing_conditions', 'critical_failures')
REQUIREMENTS_SHA256 = '84e13cc7c18b6141dfd511fa3d920a7251e592218a1de874e358e6cea86d39cf'
IDENTITY_KEYS = ('user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256')


def verified_chain(case, run):
    """Caller loads owned records; independently reject mixed receipt chains."""
    try:
        plan, result, authorization = run['plan'], run['result'], run['authorization']
        snapshot = plan['input_snapshot']
        scope = authorization['decision']
        if (run['state'] != 'completed' or result['status'] != 'completed' or plan['module_id'] != 'multi_step'
                or plan['uuid'] != run['run_id'] or encode(plan)[1] != run['plan_sha256']
                or plan['case_sha256'] != case.digest or snapshot['case'] != case.public_definition()
                or any(snapshot[key] != plan[key] or scope[key] != plan[key] for key in IDENTITY_KEYS)
                or plan['input_snapshot_id'] != snapshot['uuid'] or plan['input_snapshot_sha256'] != encode(snapshot)[1]
                or snapshot['artifact_sha256'] != encode(snapshot['artifact'])[1]
                or len(snapshot['documents']) != 1 or snapshot['documents'][0]['source_sha256'] != case.source_sha256
                or snapshot['documents'][0]['assigned_filename'] != case.source_filename
                or plan['source_document_id'] != snapshot['documents'][0]['document_id']
                or hashlib.sha256(snapshot['documents'][0]['text'].encode()).hexdigest() != snapshot['documents'][0]['text_sha256']
                or result['run_id'] != run['run_id'] or result['plan_sha256'] != run['plan_sha256']
                or authorization['run_id'] != run['run_id'] or authorization['plan_sha256'] != run['plan_sha256']
                or authorization['decision_sha256'] != encode(scope)[1] or run['scope_decision_id'] != scope['uuid']
                or run['scope_decision_sha256'] != encode(scope)[1]
                or scope['run_id'] != run['run_id'] or scope['plan_sha256'] != run['plan_sha256']
                or scope['case_sha256'] != case.digest or scope['input_snapshot_sha256'] != plan['input_snapshot_sha256']
                or scope['submission']['choice'] != 'approve' or scope['run_state_at_submission'] != 'prepared'
                or scope['submission_channel'] != 'authenticated_learner_request'
                or result['authorization_sha256'] != encode(authorization)[1]):
            raise ValueError('The run does not bind one approved owned revision and assigned source')
        events = run['stage_events']
        serialized, digest = encode(events)
        if result['stage_events_sha256'] != digest or result['stage_event_count'] != len(events):
            raise ValueError('The terminal result has different stage evidence')
        decode_checkpoints({'stage_events_json': serialized, 'stage_events_sha256': digest, 'stage_event_count': len(events)}, run)
        completed = [item for item in events if item['receipt']['kind'] == 'stage_completed']
        if (result['stage_receipt_sha256s'] != [item['receipt_sha256'] for item in completed]
                or [stage['task_type'] for stage in plan['stage_plans']] != ['Extraction', 'Prompt', 'Formatter']):
            raise ValueError('Required roles or result references differ from the actual chain')
        from app.services.workflow_engine import WorkflowEngine
        final = completed[-1]['receipt']['result']
        if result['final_output'] != WorkflowEngine()._format_final_output(final.get('formatted_output') or final.get('output')):
            raise ValueError('The final deliverable differs from the completed formatting stage')
        return snapshot, completed
    except CourseCatalogError:
        raise
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise CourseCatalogError('The connected execution evidence does not bind one complete approved chain') from exc


def check_connected_execution(contract, case, run):
    module = next((item for item in contract.modules if item.module_id == 'multi_step'), None)
    required = [item for item in module.outcomes if item.method == 'deterministic'] if module else []
    if (len(required) != 1 or required[0].id != OUTCOME_ID
            or encode({key: required[0].model_dump(mode='json')[key] for key in REQUIREMENT_KEYS})[1] != REQUIREMENTS_SHA256):
        raise CourseCatalogError('The connected-workflow requirement has no matching verified checker')
    snapshot, completed = verified_chain(case, run)
    stages = run['plan']['stage_plans']
    connected = all('step_input' in stage['effective_input_sources'] and stage['receives_previous_stage'] is True for stage in stages[1:])
    outputs = [item['receipt']['result'].get('output') for item in completed]
    nonempty = all(bool(value.strip()) if isinstance(value, str) else bool(value) for value in outputs)
    passed = connected and nonempty
    return {'outcome_id': OUTCOME_ID, 'method': 'deterministic',
            'status': 'requirements_supported' if passed else 'revision_required', 'passed': passed,
            'checker_id': 'approved-assigned-connected-chain.1', 'requirements_sha256': REQUIREMENTS_SHA256,
            'implementation_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'run_id': run['run_id'], 'plan_sha256': run['plan_sha256'], 'result_sha256': encode(run['result'])[1],
            'input_snapshot_sha256': encode(snapshot)[1], 'artifact_sha256': snapshot['artifact_sha256'],
            'case_sha256': case.digest, 'stage_events_sha256': run['result']['stage_events_sha256'],
            'authorization_sha256': run['result']['authorization_sha256'],
            'explanation': ('The same approved run connects extraction to reasoning and reasoning to its nonempty final result. '
                            'Source accuracy and the learner’s repair comparison require separate review.' if passed else
                            'The saved run bypasses a required predecessor or has an empty stage result.'),
            'revision_instruction': '' if passed else 'Inspect the saved stage inputs and outputs, correct the chain, then approve and run the new revision.',
            'credit_awarded': False, 'module_completion_eligible': False}


def compare_connected_runs(case, original, corrected):
    before, _ = verified_chain(case, original)
    after, _ = verified_chain(case, corrected)
    if (original['run_id'] == corrected['run_id'] or before['uuid'] == after['uuid']
            or any(original['plan'][key] != corrected['plan'][key] for key in IDENTITY_KEYS)
            or before['artifact_id'] != after['artifact_id']
            or any(before['documents'][0][key] != after['documents'][0][key]
                   for key in ('document_id', 'source_sha256', 'text_sha256'))):
        raise CourseCatalogError('A repair comparison requires two owned revisions of the same workflow and exact assigned input')
    before_stage, after_stage = original['plan']['stage_plans'][2], corrected['plan']['stage_plans'][2]
    return {'original_run_id': original['run_id'], 'corrected_run_id': corrected['run_id'],
            'original_result_sha256': encode(original['result'])[1], 'corrected_result_sha256': encode(corrected['result'])[1],
            'configuration_changed': before['artifact_sha256'] != after['artifact_sha256'],
            'original_formatter_rereads_source': before_stage['effective_input_sources'] == ['workflow_documents'],
            'corrected_formatter_receives_reasoning': 'step_input' in after_stage['effective_input_sources'],
            'original_final_output': original['result']['final_output'], 'corrected_final_output': corrected['result']['final_output'],
            'source_document_id': before['documents'][0]['document_id'], 'source_sha256': case.source_sha256,
            'notice': 'These are actual configuration/result differences, not a correctness judgment or learner credit.'}
