"""Bounded real extraction per assigned item with a disclosed training gate."""
from copy import deepcopy
import datetime
import time

from .attempts import encode
from .batch_case import BatchCase
from .batch_checks import check_inventory
from .batch_plan import batch_plan
from .enrollments import EnrollmentConflict


def complete_result(plan, results):
    case = BatchCase.model_validate(plan['input_snapshot']['authored_case'])
    checks = check_inventory(case, plan['input_snapshot'], results, batch_id=plan['batch_id'],
        run_id=plan['uuid'], attempt_kind=plan['phase'], source_ids=plan['source_ids'])
    return {'status': 'completed', 'item_results': deepcopy(results), 'checks': checks,
            'credit_awarded': False, 'module_completion_eligible': False}


def execute_approved_batch(run, system_config, *, checkpoint, should_stop):
    from app.services.extraction_engine import ExtractionEngine
    from .batch_approval import BatchScopeRepository
    from .batch_preparation import BatchPreparation, scope_question
    plan, authorization = run['plan'], run['authorization']
    if run['state'] != 'executing' or authorization is None:
        raise EnrollmentConflict('The exact batch action must be claimed before extraction')
    case = BatchCase.model_validate(plan['input_snapshot']['authored_case'])
    decision = authorization['decision']
    expected_claim = {'batch_id': plan['batch_id'], 'source_id': plan['failed_source_id'],
                      'run_id': run['run_id'], 'previous_retry_id': plan['previous_retry_id']}
    if (plan['phase'] == 'retry' and authorization.get('retry_claim') != expected_claim
            or plan['phase'] != 'retry' and authorization.get('retry_claim') is not None):
        raise EnrollmentConflict('Dispatch requires the exact original failed-item retry claim')
    serialized, digest = encode(decision)
    BatchScopeRepository.decode({**decision, 'record_json': serialized, 'record_sha256': digest})
    if (authorization['run_id'] != run['run_id'] or authorization['plan_sha256'] != run['plan_sha256']
            or authorization['decision_sha256'] != digest or run['scope_decision_id'] != decision['uuid']
            or run['scope_decision_sha256'] != digest or decision['submission']['choice'] != 'approve'
            or decision['plan_sha256'] != run['plan_sha256'] or decision['case_sha256'] != case.digest
            or decision['prompt'] != {**scope_question(case, plan['phase']), 'execution_choice': 'approve'}
            or any(decision[key] != plan[key] for key in ('user_id', 'enrollment_id', 'module_id', 'course_version',
                                                         'manifest_sha256', 'input_snapshot_id', 'input_snapshot_sha256'))):
        raise EnrollmentConflict('This dispatch differs from the authenticated phase-specific approval')
    parent = BatchPreparation.decode(plan['parent_run_record']) if plan['parent_run_record'] else None
    previous = BatchPreparation.decode(plan['previous_retry_record']) if plan['previous_retry_record'] else None
    config = deepcopy(system_config)
    resolved = batch_plan(plan['input_snapshot'], case, config, run_id=run['run_id'], phase=plan['phase'], parent=parent,
                          failed_source_id=plan['failed_source_id'], previous_retry=previous)
    if any(plan.get(key) != value for key, value in resolved.items()):
        raise EnrollmentConflict('The approved inputs, model settings or implementation changed')
    events, results = [], []

    def emit(value):
        if should_stop():
            raise EnrollmentConflict('Stopped batch work cannot append another item')
        event = {**value, 'run_id': run['run_id'], 'plan_sha256': run['plan_sha256'],
                 'authorization_sha256': encode(authorization)[1], 'credit_awarded': False}
        receipt = {'receipt': event, 'receipt_sha256': encode(event)[1]}
        if checkpoint(deepcopy(event), receipt['receipt_sha256']) != receipt:
            raise EnrollmentConflict('The original item checkpoint was not durably acknowledged')
        events.append(receipt)
        return receipt

    for index, item in enumerate(plan['item_plans']):
        started = emit({'kind': 'item_started', 'item_index': index, 'consumed_input': deepcopy(item),
                        'previous_receipt_sha256': events[-1]['receipt_sha256'] if events else None})
        if should_stop():
            raise EnrollmentConflict('Stopped batch work cannot begin another extraction')
        clock = time.monotonic()
        result = {key: item[key] for key in ('item_id', 'batch_id', 'run_id', 'attempt_kind', 'source_id', 'document_id', 'source_sha256')}
        result.update(artifact_sha256=plan['input_snapshot']['artifact_sha256'], status='completed', reason=None, entities=None,
            extraction_started=False, started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), usage=None, cost=None, external_effects=False)
        if plan['phase'] == 'batch' and item['source_id'] == case.controlled_failure_source_id:
            # Disclosed contained training behavior: no provider or external
            # side effect is attempted for this original rejected item.
            result.update(status='failed', reason='controlled_training_rejection_before_dispatch')
        else:
            result['extraction_started'] = True
            try:
                engine = ExtractionEngine(system_config_doc=config, domain=plan['input_snapshot']['artifact']['domain'])
                result['entities'] = engine.extract(extract_keys=deepcopy(item['field_keys']), model=plan['model_info']['model'],
                    doc_texts=deepcopy(item['doc_texts']), extraction_config_override=deepcopy(plan['effective_extraction_config']),
                    field_metadata=deepcopy(item['field_metadata']), capture_sources=True)
            except Exception:
                result.update(status='failed', reason='extraction_unavailable', entities=None)
        result.update(finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), elapsed_ms=max(0, round((time.monotonic() - clock) * 1000)))
        emit({'kind': 'item_completed', 'item_index': index, 'started_receipt_sha256': started['receipt_sha256'], 'result': result})
        results.append(result)
    return complete_result(plan, results)
