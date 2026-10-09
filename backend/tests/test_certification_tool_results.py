"""Display contracts use real authored content and reject malformed receipts."""
import inspect
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from app.services import chat_tools as tools
from app.services import certification_service as service
from app.services.certification_versions.tool_results import ProgressResult
from tests.test_chat_cert_tools import _make_context, _progress


@pytest.mark.asyncio
async def test_all_authored_chat_teaching_and_module_payloads():
    payloads = []
    with patch.object(service, 'get_progress_dict', new=AsyncMock(return_value=_progress())):
        progress = await tools.get_certification_progress(_make_context())
        assert 'error' not in progress
        payloads.append({'tool_name': 'get_certification_progress', 'content': progress})
        for mid in service.MODULE_ORDER:
            module = await tools.get_certification_module(_make_context(), mid)
            assert 'error' not in module, (mid, module)
            payloads.append({'tool_name': 'get_certification_module', 'content': module})
            lessons = service.get_lessons(mid)['lessons']
            for position in range(1, len(lessons) + 1):
                lesson = await tools.get_certification_lesson(_make_context(), mid, position)
                assert 'error' not in lesson, (mid, position, lesson)
                payloads.append({'tool_name': 'get_certification_lesson', 'content': lesson})
    assert len(payloads) == 86
    destination = os.environ.get('CERTIFICATION_CHAT_FIXTURE')
    if destination:
        Path(destination).write_text(json.dumps(payloads, indent=2, ensure_ascii=False) + '\n')


@pytest.mark.asyncio
@pytest.mark.parametrize('changes', [{'total_xp': '125'}, {'total_xp': -1}, {'certified': 'false'}, {'level': ''}, {'modules': []}, {'modules': {'foundations': {'completed': 'false'}}}])
async def test_malformed_progress_is_unconfirmed_not_zero_or_success(changes):
    with patch.object(service, 'get_progress_dict', new=AsyncMock(return_value={**_progress(), **changes})):
        saved = await tools.get_certification_progress(_make_context())
    assert saved['code'] == 'certification_response_invalid'
    assert 'do not repeat a write' in saved['hint']
    assert 'modules_completed' not in saved


@pytest.mark.asyncio
@pytest.mark.parametrize('value', [{'passed': 'false', 'stars': 1, 'checks': []}, {'passed': True, 'stars': 1, 'checks': {}}, {'passed': True, 'stars': 1, 'checks': [{'name': 'Source', 'passed': 'false', 'detail': 'Missing'}]}])
async def test_invalid_check_never_becomes_passing_card(value):
    with patch.object(service, 'validate_module', new=AsyncMock(return_value=value)) as grade:
        saved = await tools.check_certification_module(_make_context(), 'foundations')
    grade.assert_awaited_once()
    assert saved['code'] == 'certification_response_invalid'
    assert 'passed' not in saved


@pytest.mark.parametrize('change', ['valid', 'required_failed', 'false_summary', 'unknown_role', 'missing_role', 'only_advice'])
async def test_explicit_check_roles_preserve_advice_and_reject_contradictory_summary(change):
    value = {'passed': True, 'stars': 1, 'checks': [
        {'name': '15+ extraction fields', 'passed': True, 'detail': '', 'role': 'required'},
        {'name': 'Missing expected fields', 'passed': False, 'detail': 'Consider adding source context', 'role': 'advisory'},
    ]}
    if change == 'required_failed':
        value['checks'][0]['passed'] = False
    elif change == 'false_summary':
        value['passed'] = False
    elif change == 'unknown_role':
        value['checks'][1]['role'] = 'optional_failure'
    elif change == 'missing_role':
        del value['checks'][0]['role']
    elif change == 'only_advice':
        value['checks'].pop(0)
    with patch.object(service, 'validate_module', new=AsyncMock(return_value=value)):
        saved = await tools.check_certification_module(_make_context(), 'extraction_engine')
    if change == 'valid':
        assert saved['passed'] is True and saved['checks'] == value['checks']
    else:
        assert saved['code'] == 'certification_response_invalid'
        assert 'passed' not in saved


@pytest.mark.asyncio
async def test_uncertain_completion_does_not_repeat_the_already_invoked_write(caplog):
    completion = AsyncMock(return_value={'module_id': 'foundations', 'total_xp': 125, 'private_source': 'DO NOT LOG THIS SOURCE'})
    with patch.object(service, 'complete_module', new=completion):
        saved = await tools.complete_certification_module(_make_context(), 'foundations', request_id='a' * 32)
    completion.assert_awaited_once_with('user1', 'foundations', request_id='a' * 32)
    assert saved['code'] == 'certification_response_invalid'
    assert 'Work may already be saved' in saved['hint']
    assert 'private_source' not in json.dumps(saved)
    assert 'DO NOT LOG THIS SOURCE' not in caplog.text


@pytest.mark.asyncio
async def test_empty_practice_answers_produce_recovery_instead_of_blank_choices():
    with patch.object(service, 'get_lessons', return_value={'lessons': [{'title': 'Inspect', 'content': 'Read the source', 'knowledge_check': {'question': 'What next?', 'options': []}}]}):
        saved = await tools.get_certification_lesson(_make_context(), 'foundations', 1)
    assert saved['code'] == 'certification_response_invalid'


def test_course_identity_and_count_contradictions_are_rejected():
    value = {'modules': [{'module_id': 'one', 'title': 'One', 'xp': 100, 'completed': False, 'stars': 0}], 'total_xp': 0, 'level': 'novice', 'certified': False, 'modules_completed': 0, 'modules_total': 1, 'next_module_id': 'one'}
    for change in [{'certified': True}, {'modules_total': 2}, {'modules_completed': 1}, {'next_module_id': 'foreign'}, {'enrollment_id': 'e'}]:
        with pytest.raises(ValidationError):
            ProgressResult.model_validate({**value, **change})


def test_tool_signature_still_exposes_the_original_typed_arguments():
    signature = inspect.signature(tools.complete_certification_module)
    assert list(signature.parameters) == ['context', 'module_id', 'enrollment_id', 'request_id']
    assert signature.parameters['module_id'].annotation is str


@pytest.mark.parametrize('change', ['valid', 'missing_identity', 'legacy', 'modules', 'xp', 'empty_rules', 'blank_rule', 'unknown_state', 'string_outcomes'])
def test_progression_policy_cannot_contradict_the_course(change):
    policy = {'policy_id': 'required-outcomes-flexible-order.1', 'state': 'design_draft',
              'required_modules': 1, 'required_outcomes': 3, 'base_xp_total': 100, 'rules': ['Same assessed criteria.']}
    value = {'modules': [{'module_id': 'one', 'title': 'One', 'xp': 100, 'completed': False, 'stars': 0}],
             'total_xp': 0, 'level': 'novice', 'certified': False, 'modules_completed': 0,
             'modules_total': 1, 'next_module_id': 'one', 'enrollment_id': 'e', 'course_version': 'v',
             'course_title': 'Course', 'manifest_sha256': 'a' * 64, 'maximum_stars': 1,
             'credit_basis': 'required_outcomes', 'progression_policy': policy}
    if change == 'missing_identity':
        del value['enrollment_id']
    elif change == 'legacy':
        value['credit_basis'] = 'legacy_rubric'
    elif change != 'valid':
        key, replacement = {'modules': ('required_modules', 2), 'xp': ('base_xp_total', 101),
            'empty_rules': ('rules', []), 'blank_rule': ('rules', [' ']),
            'unknown_state': ('state', 'published'), 'string_outcomes': ('required_outcomes', '3')}[change]
        policy[key] = replacement
    if change == 'valid':
        assert ProgressResult.model_validate(value).progression_policy.required_outcomes == 3
    else:
        with pytest.raises(ValidationError):
            ProgressResult.model_validate(value)


@pytest.mark.parametrize('metadata', [
    {'maximum_stars': 1}, {'credit_basis': 'required_outcomes'},
    {'maximum_stars': True, 'credit_basis': 'legacy_rubric'},
    {'maximum_stars': 3, 'credit_basis': 'required_outcomes'},
    {'maximum_stars': 1, 'credit_basis': 'legacy_rubric'},
])
def test_reward_metadata_cannot_misstate_saved_credit(metadata):
    value = {'modules': [{'module_id': 'one', 'title': 'One', 'xp': 100, 'completed': True, 'stars': 2}],
             'total_xp': 100, 'level': 'novice', 'certified': True, 'modules_completed': 1,
             'modules_total': 1, 'next_module_id': None}
    with pytest.raises(ValidationError):
        ProgressResult.model_validate({**value, **metadata})
