"""Check the learner-selected Cedar Creek work sample before saving a capstone receipt."""
from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from app.models.activity import ActivityEvent
from app.models.chat import ChatConversation
from app.models.project import Project, ProjectMembership
from .attempts import encode
from .enrollments import EnrollmentConflict


if TYPE_CHECKING:
    from .catalog import CoursePackage
    from .runtime import CourseOperation
    from .scenario_assessment import ScenarioBank


class SampleSelection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project_id: str = Field(min_length=1, max_length=100)
    conversation_id: str = Field(min_length=1, max_length=100)


class SampleIncomplete(EnrollmentConflict):
    """The learner can correct a work sample before an attempt has been saved."""


def validate_case(package: CoursePackage) -> None:
    case = package.json('work-sample.json')
    required = ('module_id', 'award_module', 'policy_module', 'browser_url', 'browser_value',
                'policy_passage', 'project_title', 'award_value')
    if not isinstance(case, dict) or any(not isinstance(case.get(k), str) or not case[k].strip() for k in required):
        raise ValueError('Core requires a complete work sample definition')
    exercises = package.json('exercises.json')
    module_ids = {m.id for m in package.manifest.modules}
    if (case['module_id'] not in module_ids or any(f'assessments/{mid}.json' not in package.manifest.artifacts for mid in module_ids)
            or not all(exercises.get(case[k], {}).get('documents') for k in ('award_module', 'policy_module'))):
        raise ValueError('The work sample must bind the assigned source modules and capstone bank')


def normalized(text: str) -> str:
    return ' '.join(text.split()).casefold()


def check_case(case: dict, bank: ScenarioBank, answers: dict[str, str], context: str | None,
               messages: list[dict], award_ids: list[str], policy_ids: list[str]) -> dict:
    # Only the four selected, source-attributed statements belong in this training note.
    lines = [normalized(line) for line in (context or '').splitlines() if line.strip()]
    expected = [normalized(choice.text) for question in bank.questions for choice in question.choices
                if answers.get(question.id) == choice.id]
    if len(expected) != len(bank.questions) or sorted(lines) != sorted(expected):
        raise SampleIncomplete('Save the four selected lines, each on its own line, in the training Project context.')

    award_scoped = False
    observed: dict = {}
    for index, msg in enumerate(messages):
        if msg['role'] == 'user':
            award_scoped = any(row.get('uuid') in award_ids for row in msg.get('source_documents') or [])
            continue
        if msg['role'] != 'assistant' or msg.get('interruption'):
            continue
        if award_scoped and case['award_value'] in msg.get('content', ''):
            observed['award'] = index
        award_scoped = False
        skill = msg.get('active_skill')
        if skill and skill.get('uuid') and skill.get('version'):
            observed['skill'] = {'turn': index, 'uuid': skill['uuid'], 'version': skill['version']}
        for tool in msg.get('tool_results') or []:
            name, value = tool.get('tool_name'), tool.get('content')
            if name == 'search_knowledge_base' and isinstance(value, list):
                for hit in value:
                    if (isinstance(hit, dict) and hit.get('document_uuid') in policy_ids
                            and case['policy_passage'] in normalized(hit.get('content', ''))):
                        observed['policy'] = {'turn': index, 'document_uuid': hit['document_uuid']}
            if not isinstance(value, dict):
                continue
            if (name == 'record_value' and value.get('recorded') is True
                    and value.get('url') == case['browser_url'] and value.get('value') == case['browser_value']):
                observed['browser'] = {'turn': index, 'url': value['url'], 'value': value['value']}
                observed.pop('finish', None)
            if name == 'browser_finish' and value.get('ok') is True and value.get('working_tab') == 'closed' and 'browser' in observed:
                observed['finish'] = index
    needs = {'award': 'Ask for the authorized amount with the assigned award attached.',
             'policy': 'Search the training Knowledge Base for pre-booking approval using the assigned policy.',
             'skill': 'Select a Skill and complete a case-review turn.',
             'browser': 'Read the assigned IANA page with browser controls and record example.org.',
             'finish': 'Finish the browser task and release its working tab after recording the domain.'}
    missing = [instruction for key, instruction in needs.items() if key not in observed]
    if missing:
        raise SampleIncomplete(' '.join(missing))
    return {'note_sha256': encode(sorted(lines))[1], 'observations': observed}


async def capture_sample(operation: CourseOperation, selection: SampleSelection, bank: ScenarioBank,
                         answers: dict[str, str], case: dict) -> dict:
    user_id = operation.user_id
    project = await Project.find_one({'uuid': selection.project_id, 'owner_user_id': user_id, 'team_id': None})
    if (project is None or normalized(project.title) != normalized(case['project_title'])
            or await ProjectMembership.find_one({'project_uuid': project.uuid})):
        raise SampleIncomplete('Choose your personal, unshared Cedar Creek CC-17 training project.')
    identity = {'user_id': user_id, 'project_uuid': project.uuid, 'conversation_id': selection.conversation_id,
                'type': 'conversation'}
    if not await ActivityEvent.find_one(identity):
        raise SampleIncomplete('Choose the chat you used in this Cedar Creek project.')
    conversation = await ChatConversation.find_one({'uuid': selection.conversation_id, 'user_id': user_id})
    if conversation is None:
        raise SampleIncomplete('The selected case chat is unavailable.')
    modules = operation.progress.modules
    evidence = check_case(case, bank, answers, project.context, await conversation.get_messages(),
                          modules.get(case['award_module'], {}).get('provisioned_docs', []),
                          modules.get(case['policy_module'], {}).get('provisioned_docs', []))
    return {**selection.model_dump(), **evidence}
