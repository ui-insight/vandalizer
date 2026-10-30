"""Chat reports a learner's saved scenario answers as saved work, never as credit."""
from types import SimpleNamespace
from uuid import uuid4

from app.services import chat_tools
from app.services.certification_versions import module_readiness
from app.services.certification_versions.scenario_submissions import module_bank
from tests.integration import test_certification_chat_assessment_routing as routing
from tests.integration import test_certification_enrollments as base

repo = base.repo
pytestmark = base.pytestmark


async def test_saved_scenario_answers_are_reported_per_outcome_without_credit(repo, monkeypatch, tmp_path):
    learner, package = await routing.enroll(repo, monkeypatch, tmp_path, 'competency')
    monkeypatch.setattr(module_readiness, 'EnrollmentRepository', lambda: repo)
    context = SimpleNamespace(deps=SimpleNamespace(user_id=learner.user_id))
    before = await chat_tools.get_certification_module(context, 'ai_literacy')
    assert 'saved_assessment' not in before
    row = next(m for m in (await chat_tools.get_certification_progress(context))['modules'] if m['module_id'] == 'ai_literacy')
    assert 'saved_assessment' not in row

    bank = module_bank(package, 'ai_literacy')
    answers = {question.id: question.correct_choice_id for question in bank.questions}
    # One deliberately wrong choice leaves exactly its outcome needing revision.
    missed = bank.questions[0]
    answers[missed.id] = next(choice.id for choice in missed.choices if choice.id != missed.correct_choice_id)
    saved = await base.submit_scenario(repo, learner, package, bank, answers, uuid4().hex)

    after = await chat_tools.get_certification_module(context, 'ai_literacy')
    states = {item['outcome_id']: item['state'] for item in after['saved_assessment']['outcomes']}
    assert after['saved_assessment']['scenario_attempt_id'] == saved['attempt_id']
    assert states[missed.outcome_id] == 'revision_required'
    assert set(states.values()) <= {'supported', 'revision_required'} and len(states) == 3
    assert after['saved_assessment']['status'] == 'revision_required'
    assert after['saved_assessment']['credit_awarded'] is False and after['completed'] is False
    row = next(m for m in (await chat_tools.get_certification_progress(context))['modules'] if m['module_id'] == 'ai_literacy')
    assert row['saved_assessment'] == after['saved_assessment'] and row['completed'] is False
    assert 'submits new answers' in after['saved_assessment']['next_step']
    assert (await repo.read_progress(learner.user_id, learner.uuid)).total_xp == 0


async def test_an_unreadable_saved_assessment_is_reported_and_does_not_block_the_module(repo, monkeypatch, tmp_path):
    from app.models.certification import CertificationScenarioAttempt
    learner, package = await routing.enroll(repo, monkeypatch, tmp_path, 'competency')
    monkeypatch.setattr(module_readiness, 'EnrollmentRepository', lambda: repo)
    bank = module_bank(package, 'ai_literacy')
    saved = await base.submit_scenario(repo, learner, package, bank,
        {question.id: question.correct_choice_id for question in bank.questions}, uuid4().hex)
    await CertificationScenarioAttempt.get_motor_collection().delete_many({'uuid': saved['attempt_id']})
    result = await chat_tools.get_certification_module(SimpleNamespace(deps=SimpleNamespace(user_id=learner.user_id)), 'ai_literacy')
    assert result['lesson_titles'] and result['saved_assessment'] == {
        'scenario_attempt_id': saved['attempt_id'], 'status': 'unavailable', 'outcomes': [], 'credit_awarded': False,
        'next_step': 'The saved answers could not be read. The learner reopens the module in the Certification panel.'}
