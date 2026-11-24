"""Complete preview assembly remains reproducible, isolated and non-enrollable."""
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

from app.services.certification_versions.authoring import choose_default, publish
from app.services.certification_versions.catalog import CATALOG_ROOT, CourseCatalog, CourseCatalogError

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('certification_v5_preview', ROOT / 'scripts/assemble_certification_v5_preview.py')
preview = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preview)
VERSION = 'v5.0-isolated-test.1'


def test_full_preview_uses_every_new_lesson_and_assessment_without_touching_application_catalog(tmp_path):
    registry = (CATALOG_ROOT / 'registry.json').read_bytes()
    output = preview.assemble(tmp_path / 'first', VERSION, track='advanced')
    preview.assemble(tmp_path / 'second', VERSION, track='advanced')
    package = CourseCatalog(output).load(VERSION, preview=True)
    second = CourseCatalog(tmp_path / 'second').load(VERSION, preview=True)
    assert package.manifest_bytes == second.manifest_bytes
    assert package.artifact_bytes == second.artifact_bytes
    public = json.loads((output / 'public-course.json').read_text())
    report = json.loads((output / 'preview-report.json').read_text())
    assert public['prerequisites'] == {module.id: list(module.prerequisites) for module in package.manifest.modules}
    assert public['levels'] == package.json('course-structure.json')['levels']
    assert public['tiers'] == package.json('course-structure.json')['tiers']
    assert public['progression_policy']['required_outcomes'] == 33
    assert public['progression_policy']['required_modules'] == 11
    assert public['progression_policy']['base_xp_total'] == 1850
    assert public['progression_policy']['state'] == 'design_draft'
    assert report['progression_policy_id'] == 'required-outcomes-flexible-order.1'
    assert 'progression-policy.json' in package.manifest.artifacts
    assert (report['modules'], report['lessons'], report['required_outcomes']) == (11, 74, 33)
    assert report['release_verified_outcomes'] == 0
    for key in ('grading_available', 'enrollment_available', 'application_registry_changed', 'credit_policy_finalized', 'progression_policy_finalized'):
        assert report[key] is False
    expected = {'ai_literacy': 'scenarioAssessment', 'foundations': 'practicalPreparation',
                'process_mapping': 'processAssessment', 'workflow_design': 'workflowDesignAssessment',
                'extraction_engine': 'repairAssignment', 'multi_step': 'connectedWorkflowAssessment',
                'advanced_nodes': 'budgetWorkflowAssessment', 'output_delivery': 'outputWorkflowAssessment',
                'validation_qa': 'validationAssessment', 'batch_processing': 'batchAssessment',
                'governance': 'governanceAssessment'}
    for module in public['modules']:
        assert module[expected[module['id']]]
        assert module['assessment'] is None
        authored = json.loads((preview.DATA / f'drafts/v5.0/{module["id"].replace("_", "-")}-teaching.json').read_text())
        assert module['description'] == authored['module_patch']['description']
        assert [(lesson['id'], lesson['revision'], lesson['content']) for lesson in module['lessons']] == [
            (lesson['id'], lesson['revision'], lesson['content']) for lesson in authored['replacements']]
        exercise = package.json('exercises.json')[module['id']]
        assert exercise['expected_values'] == exercise['star_criteria'] == {}
    for module in ('validation_qa', 'governance'):
        assert next(item for item in public['modules'] if item['id'] == module)['scenarioAssessment']
    serialized = json.dumps(public)
    assert 'correct_choice_id' not in serialized and 'review_guidance' not in serialized
    for new_enrollment in (False, True):
        with pytest.raises(CourseCatalogError, match='Draft'):
            CourseCatalog(output).load(VERSION, new_enrollment=new_enrollment)
    with pytest.raises(CourseCatalogError):
        choose_default(CourseCatalog(output), VERSION)
    before = (output / 'registry.json').read_bytes()
    with pytest.raises(CourseCatalogError):
        publish(CourseCatalog(output), VERSION, expected_digest=package.manifest_sha256)
    assert (output / 'registry.json').read_bytes() == before
    assert (CATALOG_ROOT / 'registry.json').read_bytes() == registry
    assert set(json.loads(before)) == {'schema_version', 'releases'}
    with pytest.raises(ValueError, match='new output'):
        preview.assemble(output, VERSION, track='advanced')


@pytest.mark.parametrize('location', [CATALOG_ROOT, CATALOG_ROOT / 'unapproved-preview'])
def test_preview_cannot_write_to_application_registry(location):
    with pytest.raises(ValueError, match='outside'):
        preview.assemble(location, VERSION, track='advanced')


@pytest.mark.parametrize('problem', ['missing_case', 'mismatched_case', 'stale_lesson', 'legacy_scoring', 'stale_scenario_bank'])
def test_incomplete_or_contradictory_preview_leaves_no_partial_output(tmp_path, problem):
    data = tmp_path / 'data'
    data.mkdir()
    for name in ('lessons.json', 'panel-modules.json', 'course-structure.json'):
        shutil.copyfile(preview.DATA / name, data / name)
    shutil.copytree(preview.DATA / 'documents', data / 'documents')
    shutil.copytree(preview.DATA / 'drafts', data / 'drafts')
    draft = data / 'drafts/v5.0'
    if problem == 'missing_case':
        (draft / 'governance-capstone-case.json').unlink()
    elif problem == 'stale_scenario_bank':
        path = draft / 'ai-literacy-exercise.json'
        value = json.loads(path.read_text())
        value['scenario_bank_sha256'] = '0' * 64
        path.write_text(json.dumps(value))
    elif problem == 'stale_lesson':
        path = draft / 'foundations-teaching.json'
        value = json.loads(path.read_text())
        value['replacements'][0]['revision'] = 1
        path.write_text(json.dumps(value))
    else:
        path = draft / 'foundations-exercise.json'
        value = json.loads(path.read_text())
        if problem == 'legacy_scoring':
            value['star_criteria'] = {'1': 'Three fields earn credit'}
        else:
            value['scope_proposal_sha256'] = '0' * 64
        path.write_text(json.dumps(value))
    with pytest.raises((ValueError, FileNotFoundError)):
        preview.assemble(tmp_path / 'output', VERSION, track='advanced', data_root=data)
    assert not (tmp_path / 'output').exists()
    assert not list(tmp_path.glob('.certification-preview-*'))


def test_core_is_the_default_and_packages_only_its_own_sources(tmp_path):
    from app.services.certification_versions.scenario_submissions import module_bank
    output = preview.assemble(tmp_path / 'core', VERSION)
    course = json.loads((output / 'public-course.json').read_text())
    report = json.loads((output / 'preview-report.json').read_text())
    assert (report['track'], report['modules'], report['lessons'], report['required_outcomes']) == ('core', 6, 12, 9)
    assert sum(m['estimatedMinutes'] for m in course['modules']) == 41
    assert course['modules'][0]['id'] == 'core_chat'
    assert course['modules'][-1]['scenarioAssessment']['work_sample_project'] == 'Cedar Creek CC-17'
    package = CourseCatalog(output).load(VERSION, preview=True)
    assert set(package.json('exercises.json')) == {m['id'] for m in course['modules']}
    assert set((output / VERSION / 'documents').iterdir()) == {
        output / VERSION / 'documents' / name for name in ('cedar-creek-award.pdf', 'training-travel-policy.pdf')}
    assert package.json('exercises.json')['core_chat']['lab_used_in_lessons'] is True
    for module in course['modules']:
        bank = module_bank(package, module['id'])
        assert 'correct_choice_id' not in json.dumps(module)
        assert bank.grade({}, expected_sha256=bank.digest)['passed'] is False


@pytest.mark.parametrize('missing', ['award', 'knowledge_base', 'skill', 'record', 'finish'])
def test_core_note_requires_each_observed_action(tmp_path, missing):
    from app.services.certification_versions.core_work_sample import SampleIncomplete, check_case
    from app.services.certification_versions.scenario_submissions import module_bank
    output = preview.assemble(tmp_path / 'core', VERSION)
    package = CourseCatalog(output).load(VERSION, preview=True)
    case = package.json('work-sample.json')
    bank = module_bank(package, case['module_id'])
    answers = {q.id: q.correct_choice_id for q in bank.questions}
    note = '\n'.join(c.text for q in bank.questions for c in q.choices if c.id == answers[q.id])
    messages = [{'role': 'user', 'source_documents': [{'uuid': 'other' if missing == 'award' else 'award'}]},
                {'role': 'assistant', 'content': 'The award authorizes $48,000.',
                 'active_skill': None if missing == 'skill' else {'uuid': 'skill', 'version': '1'},
                 'tool_results': [
                     {'tool_name': 'search_knowledge_base', 'content': [
                         {'document_uuid': 'other' if missing == 'knowledge_base' else 'policy', 'content': case['policy_passage']}]},
                     {'tool_name': 'record_value', 'content': {'recorded': True, 'value': case['browser_value'],
                      'url': 'https://example.org' if missing == 'record' else case['browser_url']}},
                     {'tool_name': 'browser_finish', 'content': {'ok': True, 'working_tab': 'kept' if missing == 'finish' else 'closed'}}]}]
    with pytest.raises(SampleIncomplete):
        check_case(case, bank, answers, note, messages, ['award'], ['policy'])


@pytest.fixture(scope='module')
def core_case(tmp_path_factory):
    from app.services.certification_versions.scenario_submissions import module_bank
    output = preview.assemble(tmp_path_factory.mktemp('core-case') / 'core', VERSION)
    package = CourseCatalog(output).load(VERSION, preview=True)
    case = package.json('work-sample.json')
    bank = module_bank(package, case['module_id'])
    answers = {q.id: q.correct_choice_id for q in bank.questions}
    return case, bank, answers, [c.text for q in bank.questions for c in q.choices if c.id == answers[q.id]]


def core_sample(core_case, *, note=None, reply='The award authorizes $48,000.', value='example.org', url=None,
                tab='closed', policy='tool'):
    """Grade one synthetic chat; return None when accepted, else the learner message."""
    from app.services.certification_versions.core_work_sample import SampleIncomplete, check_case
    case, bank, answers, lines = core_case
    passage = {'document_uuid': 'policy', 'content': 'Obtain written approval before booking travel.',
               'content_preview': 'Obtain written approval before booking travel.'}
    messages = [{'role': 'user', 'source_documents': [{'uuid': 'award'}]},
                {'role': 'assistant', 'content': reply, 'active_skill': {'uuid': 'skill', 'version': '1'},
                 'citations': [passage] if policy == 'attached' else [],
                 'tool_results': [
                     {'tool_name': 'search_knowledge_base', 'content': [passage] if policy == 'tool' else []},
                     {'tool_name': 'record_value', 'content': {'recorded': True, 'value': value, 'url': url or case['browser_url']}},
                     {'tool_name': 'browser_finish', 'content': {'ok': True, 'working_tab': tab}}]}]
    try:
        check_case(case, bank, answers, '\n'.join(lines) if note is None else note, messages, ['award'], ['policy'])
    except SampleIncomplete as exc:
        return str(exc)
    return None


@pytest.mark.parametrize('reply', [
    'The sponsor authorizes $48,000.', 'Authorized: **$48,000.00**', 'It authorizes USD 48,000 (page 1).',
    'The notice authorizes 48,000 dollars for CC-17.', r'The amount is \$48,000, on page 1.', 'US$48,000', '$48K'])
def test_core_award_answer_accepts_the_amount_however_it_is_written(core_case, reply):
    assert core_sample(core_case, reply=reply) is None


@pytest.mark.parametrize('reply', [
    '$48,000,000', 'The award authorizes $480,000.', 'It authorizes $148,000.', 'USD 4,800',
    'It is not $48,000; it is $480,000,000.', 'The notice gives no amount.'])
def test_core_award_answer_rejects_another_amount(core_case, reply):
    assert 'authorized amount' in core_sample(core_case, reply=reply)


@pytest.mark.parametrize('value, url', [
    ('Example.org', None), (' example.org. ', None), ('example.org', 'https://WWW.IANA.org/help/example-domains/')])
def test_core_browser_record_ignores_case_spacing_and_a_trailing_dot_or_slash(core_case, value, url):
    assert core_sample(core_case, value=value, url=url) is None


@pytest.mark.parametrize('value, url', [
    ('example.com and example.org', None), ('example.com', None), ('example.org', 'https://www.iana.org/help/other'),
    ('example.org', 'https://example.org/help/example-domains')])
def test_core_browser_record_still_needs_the_one_domain_on_the_assigned_page(core_case, value, url):
    assert 'IANA' in core_sample(core_case, value=value, url=url)


@pytest.mark.parametrize('tab', ['none', 'kept'])
def test_core_browser_task_is_unfinished_until_the_assistant_closes_its_tab(core_case, tab):
    assert 'let the assistant close it' in core_sample(core_case, tab=tab)


def test_core_policy_passage_counts_when_an_attached_knowledge_base_supplied_it(core_case):
    assert core_sample(core_case, policy='attached') is None
    assert 'Knowledge Base' in core_sample(core_case, policy='none')


@pytest.mark.parametrize('style', ['- {}', '* {}', '• {}', '  {}  ', '{}.', '-   {}'])
def test_core_note_accepts_list_markers_spacing_and_either_final_period(core_case, style):
    lines = [style.format(line.rstrip('.')) for line in core_case[3]]
    assert core_sample(core_case, note='\n\n'.join(lines)) is None


@pytest.mark.parametrize('change', ['heading', 'reworded', 'missing', 'wrong_choice'])
def test_core_note_still_needs_exactly_the_selected_statements(core_case, change):
    case, bank, answers, lines = core_case
    lines = list(lines)
    if change == 'heading':
        lines.insert(0, 'Case note')
    elif change == 'reworded':
        lines[0] = lines[0].replace('authorizes', 'requests')
    elif change == 'missing':
        lines.pop()
    else:
        lines[0] = next(c.text for c in bank.questions[0].choices if c.id != answers[bank.questions[0].id])
    assert 'four selected lines' in core_sample(core_case, note='\n'.join(lines))


@pytest.mark.parametrize('link, shared', [
    ({}, True), ({'revoked': True}, False), ({'expired': True}, False), ({'max_uses': 1, 'use_count': 1}, False),
    ({'max_uses': 2, 'use_count': 1}, True), (None, False)])
async def test_core_sample_project_with_a_usable_invite_link_is_shared(core_case, monkeypatch, link, shared):
    import datetime
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from app.models.project import ProjectJoinLink
    from app.services.certification_versions import core_work_sample as sample
    case, bank, answers, lines = core_case
    project = SimpleNamespace(uuid='project', title=case['project_title'], context='\n'.join(lines))
    links = []
    if link is not None:
        fields = {'revoked': False, 'max_uses': None, 'use_count': 0, **link}
        hours = -1 if fields.pop('expired', False) else 1
        links = [ProjectJoinLink.model_construct(project_uuid='project', token='t', created_by='learner',
                                                 expires_at=datetime.datetime.now() + datetime.timedelta(hours=hours), **fields)]
    found = SimpleNamespace(to_list=AsyncMock(return_value=links))
    monkeypatch.setattr(sample, 'Project', SimpleNamespace(find_one=AsyncMock(return_value=project)))
    monkeypatch.setattr(sample, 'ProjectMembership', SimpleNamespace(find_one=AsyncMock(return_value=None)))
    monkeypatch.setattr(sample, 'ProjectJoinLink', SimpleNamespace(find=lambda query: found))
    # Stop at the next lookup: reaching it means the project was accepted as private.
    monkeypatch.setattr(sample, 'ActivityEvent', SimpleNamespace(find_one=AsyncMock(return_value=None)))
    operation = SimpleNamespace(user_id='learner', progress=SimpleNamespace(modules={}))
    with pytest.raises(sample.SampleIncomplete, match='unshared' if shared else 'chat you used'):
        await sample.capture_sample(operation, sample.SampleSelection(project_id='project', conversation_id='chat'), bank, answers, case)
