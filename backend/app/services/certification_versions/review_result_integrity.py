"""Check saved review semantics before displaying or consuming an assessment.

Record digests establish which bytes were saved. They do not establish that a
producer returned a complete, consistent assessment. This check never invokes a
judge, changes a receipt, awards credit or creates a staff-review task.
"""
from .attempts import encode
from .automatic_review import AutomaticReviewPolicy, OutcomeDecision, review_packet, validate_decisions
from .catalog import CourseCatalogError
from .review_attempts import ReviewAttemptRepository


def validate_saved_review_result(saved, contract):
    try:
        _validate(saved, contract)
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        raise CourseCatalogError('The saved assessment result needs reconciliation before it can be displayed') from exc


def _validate(saved, contract):
    if saved['result'] is None:
        if saved['state'] not in ('prepared', 'evaluating'):
            raise ValueError('A terminal review needs its original result')
        return
    record = saved['record']
    result = saved['result']['assessment']
    status = result['status']
    expected_pass = {'requirements_supported': True, 'revision_required': False, 'grading_unavailable': None}
    if status not in expected_pass or result.get('passed') is not expected_pass[status]:
        raise ValueError('Assessment status contradicts its pass value')
    if any(result.get(key) is not False for key in ('credit_awarded', 'module_completion_eligible', 'staff_review_required')):
        raise ValueError('Draft feedback cannot award credit or request staff grading')
    policy = AutomaticReviewPolicy().model_dump(mode='json')
    if encode(record['policy'])[1] != encode(policy)[1]:
        raise ValueError('Unsupported assessment policy')
    required, evidence, digest = review_packet(contract, record['module_id'], record['evidence'])
    module = next(item for item in contract.modules if item.module_id == record['module_id'])
    provenance = record.get('provenance', {})
    deterministic = provenance.get('deterministic_outcomes', [])
    expected_deterministic = {item.id for item in module.outcomes if item.method == 'deterministic'}
    if (not isinstance(deterministic, list)
            or len(deterministic) != len(expected_deterministic)
            or {item['outcome_id'] for item in deterministic} != expected_deterministic
            or any(type(item['passed']) is not bool for item in deterministic)
            or encode(result.get('deterministic_outcomes', []))[1] != encode(deterministic)[1]):
        raise ValueError('Deterministic outcome checks must retain the original complete set')
    supporting = provenance.get('supporting_checks', [])
    if (not isinstance(supporting, list)
            or len({item['outcome_id'] for item in supporting}) != len(supporting)
            or any(item['outcome_id'] not in {outcome.id for outcome in required}
                   or type(item['passed']) is not bool for item in supporting)
            or encode(result.get('supporting_checks', []))[1] != encode(supporting)[1]):
        raise ValueError('Supporting checks must retain their original required outcome and verdict')
    if status == 'grading_unavailable':
        if result.get('outcomes', []) or result.get('model_outcomes', []):
            raise ValueError('A technical failure cannot contain a successful model assessment')
        return
    identity = {'module_id': module.module_id, 'rubric_id': contract.rubric_id,
                'contract_sha256': encode(contract.model_dump(mode='json'))[1],
                'evidence_sha256': digest, 'policy_id': policy['policy_id'],
                'policy_sha256': encode(policy)[1]}
    if any(result.get(key) != value for key, value in identity.items()):
        raise ValueError('The assessment must match its original requirements and evidence')
    ids = result['assessed_outcome_ids']
    if not isinstance(ids, list) or len(ids) != len(set(ids)) or set(ids) != {item.id for item in required} | expected_deterministic:
        raise ValueError('Unexpected assessed outcome coverage')
    raw = result['model_outcomes'] if 'supporting_checks' in provenance else result['outcomes']
    if not isinstance(raw, list):
        raise ValueError('Outcome decisions must be a list')
    decisions = tuple(OutcomeDecision.model_validate(item) for item in raw)
    decision_ids = [item.outcome_id for item in decisions]
    not_evaluated = result.get('not_evaluated_outcome_ids', [])
    if (not isinstance(not_evaluated, list) or len(not_evaluated) != len(set(not_evaluated))
            or set(decision_ids) & set(not_evaluated)
            or set(decision_ids) | set(not_evaluated) != {item.id for item in required}):
        raise ValueError('Missing or unrelated outcome decisions')
    if not_evaluated and (status != 'revision_required' or result.get('model_called') is not False):
        raise ValueError('Incomplete evidence cannot claim a completed model assessment')
    if result.get('model_called') is True:
        if encode(result.get('reviewer'))[1] != encode(record['reviewer'])[1]:
            raise ValueError('The assessment judge differs from the saved request')
    elif result.get('model_called') is not False or status == 'requirements_supported':
        raise ValueError('Unsupported model execution claim')
    else:
        kinds = {item.kind for item in evidence}
        missing = {item.id for item in required if not set(item.evidence) <= kinds}
        if set(decision_ids) != missing or any(item.verdict != 'unclear' or item.citations for item in decisions):
            raise ValueError('A missing-evidence response cannot invent a model verdict')
    # Validate the original model verdict before applying source/arithmetic
    # vetoes; a deterministic failure may intentionally replace its citations.
    from types import SimpleNamespace
    validate_decisions(SimpleNamespace(outcomes=decisions),
                       tuple(item for item in required if item.id in decision_ids), evidence)
    model_passed = not not_evaluated and bool(decisions) and all(item.verdict == 'supported' for item in decisions)
    expected = ReviewAttemptRepository.with_saved_checks(saved, {
        **result, 'outcomes': raw, 'passed': model_passed,
        'status': 'requirements_supported' if model_passed else 'revision_required',
    })
    if any(expected[key] != result[key] for key in ('outcomes', 'passed', 'status')):
        raise ValueError('The summary does not reflect the saved model and deterministic checks')
