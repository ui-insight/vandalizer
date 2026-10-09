"""Run each complete assigned source through the real extraction engine once."""
from copy import deepcopy

from .attempts import encode
from .enrollments import EnrollmentConflict
from .validation_case import ValidationCase
from .validation_checks import check_repair, check_suite
from .validation_plan import validation_plan


def complete_result(plan, results):
    from .validation_preparation import ValidationPreparation
    case = ValidationCase.model_validate(plan['input_snapshot']['authored_case'])
    checks = check_suite(case, plan['input_snapshot'], plan['suite']['test_cases'], results)
    repair = None
    if plan['phase'] == 'retest':
        original = ValidationPreparation.decode(plan['original_run_record'])
        repair = check_repair(case, original['plan']['input_snapshot'], plan['input_snapshot'],
            original['plan']['suite']['test_cases'], plan['suite']['test_cases'], original['result']['case_results'], results)
    return {'status': 'completed', 'case_results': deepcopy(results), 'checks': checks, 'repair_checks': repair,
            'credit_awarded': False, 'module_completion_eligible': False}


def execute_approved_suite(run, system_config, *, checkpoint, should_stop):
    from app.services.extraction_engine import ExtractionEngine
    from .validation_approval import ValidationScopeRepository
    from .validation_preparation import SCOPE_QUESTION, ValidationPreparation
    plan, authorization = run['plan'], run['authorization']
    if run['state'] != 'executing' or authorization is None:
        raise EnrollmentConflict('The suite must have an authenticated claim before provider execution')
    decision = authorization['decision']
    serialized, digest = encode(decision)
    ValidationScopeRepository.decode({**decision, 'record_json': serialized, 'record_sha256': digest})
    if (authorization['run_id'] != run['run_id'] or authorization['plan_sha256'] != run['plan_sha256']
            or authorization['decision_sha256'] != digest or run['scope_decision_id'] != decision['uuid']
            or run['scope_decision_sha256'] != digest or decision['submission']['choice'] != 'approve'
            or decision['plan_sha256'] != run['plan_sha256'] or decision['case_sha256'] != plan['case_sha256']
            or decision['prompt'] != {**SCOPE_QUESTION, 'execution_choice': 'approve'}
            or any(decision[key] != plan[key] for key in ('user_id', 'enrollment_id', 'module_id', 'course_version',
                                                        'manifest_sha256', 'input_snapshot_id', 'input_snapshot_sha256'))):
        raise EnrollmentConflict('This execution does not bind the exact authenticated suite approval')
    case = ValidationCase.model_validate(plan['input_snapshot']['authored_case'])
    original = ValidationPreparation.decode(plan['original_run_record']) if plan['original_run_record'] else None
    config = deepcopy(system_config)
    resolved = validation_plan(plan['input_snapshot'], plan['suite'], case, config, original_run=original)
    if any(plan[key] != value for key, value in resolved.items()):
        raise EnrollmentConflict('The approved suite, inputs, runtime or implementation changed')
    events, results = [], []

    def emit(value):
        if should_stop():
            raise EnrollmentConflict('Stopped validation work cannot append another case')
        event = {**value, 'run_id': run['run_id'], 'plan_sha256': run['plan_sha256'],
                 'authorization_sha256': encode(authorization)[1], 'credit_awarded': False}
        receipt = {'receipt': event, 'receipt_sha256': encode(event)[1]}
        if checkpoint(deepcopy(event), receipt['receipt_sha256']) != receipt:
            raise EnrollmentConflict('The case checkpoint was not durably acknowledged')
        events.append(receipt)
        return receipt

    for index, stage in enumerate(plan['case_plans']):
        started = emit({'kind': 'case_started', 'case_index': index, 'consumed_input': deepcopy(stage),
                        'previous_receipt_sha256': events[-1]['receipt_sha256'] if events else None})
        if should_stop():
            raise EnrollmentConflict('Stopped validation work cannot start another provider call')
        result = {'source_id': stage['source_id'], 'source_sha256': stage['source_sha256'],
                  'artifact_sha256': plan['input_snapshot']['artifact_sha256'], 'status': 'completed', 'reason': None}
        try:
            engine = ExtractionEngine(system_config_doc=config, domain=plan['input_snapshot']['artifact']['domain'])
            result['entities'] = engine.extract(extract_keys=deepcopy(stage['field_keys']), model=plan['model_info']['model'],
                doc_texts=deepcopy(stage['doc_texts']), extraction_config_override=deepcopy(plan['effective_extraction_config']),
                field_metadata=deepcopy(stage['field_metadata']), capture_sources=True)
        except Exception:
            # Never persist provider exception text (which may include secrets).
            result.update(status='unavailable', entities=None, reason='extraction_unavailable')
        emit({'kind': 'case_completed', 'case_index': index, 'started_receipt_sha256': started['receipt_sha256'], 'result': result})
        if result['status'] != 'completed':
            raise EnrollmentConflict('The extraction is unavailable; no successor was dispatched')
        results.append(result)
    return complete_result(plan, results)
