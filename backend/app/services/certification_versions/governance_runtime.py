"""Execute one approved six-field interpretation of both complete source records."""
from copy import deepcopy

from .attempts import encode
from .enrollments import EnrollmentConflict
from .governance_case import GovernanceCase
from .governance_checks import check_result
from .governance_plan import governance_plan


def complete_result(plan, extraction):
    checks = check_result(GovernanceCase.model_validate(plan['input_snapshot']['authored_case']),
        plan['input_snapshot'], extraction, run_id=plan['uuid'], phase=plan['phase'])
    repair_checks = None
    if plan['phase'] == 'repair':
        from .governance_preparation import GovernancePreparation
        from .governance_checks import compare_repair
        original = GovernancePreparation.decode(plan['source_finding']['execution'])
        repair_checks = compare_repair(GovernanceCase.model_validate(plan['input_snapshot']['authored_case']), original,
            {'state': 'completed', 'run_id': plan['uuid'], 'plan': plan, 'result': {'extraction': extraction}})
    return {'status': 'completed', 'extraction': deepcopy(extraction), 'checks': checks, 'repair_checks': repair_checks,
        'credit_awarded': False, 'module_completion_eligible': False}


def execute_approved_capstone(run, system_config, *, checkpoint, should_stop):
    from app.services.extraction_engine import ExtractionEngine
    from .governance_preparation import validate_authorization
    plan = run['plan']
    if run['state'] != 'executing' or run['authorization'] is None:
        raise EnrollmentConflict('The exact capstone requires a saved authenticated execution claim')
    validate_authorization(run)
    case = GovernanceCase.model_validate(plan['input_snapshot']['authored_case'])
    config = deepcopy(system_config)
    current = governance_plan(plan['input_snapshot'], plan['scope_correction'], case, config, run_id=run['run_id'], finding=plan['source_finding'])
    if any(plan[key] != value for key, value in current.items()):
        raise EnrollmentConflict('The approved capstone source, revision, model or implementation changed')

    def emit(value):
        if should_stop():
            raise EnrollmentConflict('Stopped work cannot append execution evidence')
        event = {**value, 'extraction_index': 0, 'run_id': run['run_id'], 'plan_sha256': run['plan_sha256'],
            'authorization_sha256': encode(run['authorization'])[1], 'credit_awarded': False}
        receipt = {'receipt': event, 'receipt_sha256': encode(event)[1]}
        if checkpoint(deepcopy(event), receipt['receipt_sha256']) != receipt:
            raise EnrollmentConflict('The complete extraction input or output was not durably acknowledged')
        return receipt

    stage = plan['extraction_input']
    started = emit({'kind': 'extraction_started', 'consumed_input': deepcopy(stage), 'previous_receipt_sha256': None})
    if should_stop():
        raise EnrollmentConflict('Stopped work cannot begin a provider call')
    result = {'run_id': run['run_id'], 'phase': plan['phase'], 'artifact_sha256': stage['artifact_sha256'],
        'source_sha256s': stage['source_sha256s'], 'status': 'completed', 'reason': None, 'credit_awarded': False}
    try:
        engine = ExtractionEngine(system_config_doc=config, domain=plan['input_snapshot']['artifact']['domain'])
        result['entities'] = engine.extract(extract_keys=deepcopy(stage['field_keys']), model=plan['model_info']['model'],
            doc_texts=deepcopy(stage['doc_texts']), extraction_config_override=deepcopy(plan['effective_extraction_config']),
            field_metadata=deepcopy(stage['field_metadata']), capture_sources=True)
        if engine.skipped_doc_indices:
            raise ValueError('The complete joint source was not processed')
    except Exception:
        # Provider exceptions may contain credentials; only a bounded reason is saved.
        result.update(status='failed', entities=None, reason='extraction_unavailable')
    emit({'kind': 'extraction_completed', 'started_receipt_sha256': started['receipt_sha256'], 'result': result})
    if result['status'] != 'completed':
        raise EnrollmentConflict('Extraction is unavailable; no semantic failure or repair is inferred')
    return complete_result(plan, result)
